"""OAST na varredura (V1.12, F2 e F3, ADR 0099 e 0100): C11 do crAPI, só no laboratório.

Nível RÁPIDO: uma pilha crAPI por cenário, `probe` e `scan` só da operação do C11
(`contact_mechanic`, o campo `mechanic_api`), com o retorno pela ponte interna do ADR 0095. O papel
da carta é feito na CÓPIA descartável do perfil: escopo mínimo (login, veículos, saúde e a
operação, `GET` e `POST`), a operação fora do `deny_paths` e `scan.oast: true` (cenário ligado).

- ligado: o ZAP aponta o Callback para a ponte, a CLI manda a URL de retorno no campo e o retorno
  observado vira achado de SSRF com a prova do evento;
- desligado: nenhum tráfego de OAST (contador e histórico do ZAP em zero) e nenhum achado de OAST;
- nos dois: o ZAP continua numa rede interna e nada sai da máquina (rota externa recusada).

Medidas (não asserções) vão para `HDAST_IT_METRICS_DIR/lab-oast-scan-*`.
"""

import json
import secrets
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import REPO, LabCli, proxy_audit, require_docker
from tests.integration.oast_support import OastLab
from tests.integration.run_support import record_metrics
from tests.integration.test_lab_oast import finish_proof

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

OPERATION = "contact_mechanic"
FIELD = "mechanic_api"
OAST_PLUGIN = "hdast-oast-ssrf"
MECHANIC_API = "http://localhost:8000/workshop/api/mechanic/receive_report"
OAST_TYPE = "22"


@dataclass
class OastScanLab:
    """O que um cenário produziu."""

    enabled: bool
    run_id: str = ""
    scan: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    interactions_before: int = 0
    interactions_after: int = 0
    oast_messages: int = 0
    exit_codes: dict[str, int] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    proxy_rows: int = 0


def _tweak_profile(product: Path, *, oast: bool) -> None:
    """Escopo mínimo, a operação do C11 liberada e a chave (papel da carta) só na cópia."""
    target = product / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    rule = data["scope"]["allow"][0]
    rule["paths"] = [
        "/identity/api/auth/login",
        "/identity/api/v2/vehicle/vehicles",
        "/workshop/api/merchant/contact_mechanic",
        "/workshop/api/shop/products",
    ]
    rule["methods"] = ["GET", "POST"]
    data["scope"]["allow"] = [rule]
    data["scope"]["deny_paths"] = [
        item for item in data["scope"]["deny_paths"] if "contact_mechanic" not in item
    ]
    scan = data.setdefault("scan", {})
    if oast:
        scan["oast"] = True
    else:
        scan.pop("oast", None)
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    rules = yaml.safe_load((product / "data-rules.yml").read_text(encoding="utf-8"))
    # O OpenAPI declara `number_of_repeats` como `number`, mas o alvo exige inteiro.
    for name, value in (
        ("mechanic_code", "TRAC_JHN"),
        (FIELD, MECHANIC_API),
        ("number_of_repeats", 1),
    ):
        rules["rules"].append(
            {
                "match": {"operation": OPERATION, "field": name},
                "generator": "constant",
                "args": {"value": value},
            }
        )
    (product / "data-rules.yml").write_text(
        yaml.safe_dump(rules, allow_unicode=True), encoding="utf-8"
    )
    flows = yaml.safe_load((product / "flows.yml").read_text(encoding="utf-8"))
    for binding in flows["bindings"]:
        if binding["produces"] == {"operation": "get_vehicles", "field": "0.vin"}:
            binding["consumed_by"].append({"operation": OPERATION, "field": "vin"})
    (product / "flows.yml").write_text(yaml.safe_dump(flows, allow_unicode=True), encoding="utf-8")


def _oast_messages(lab: OastLab) -> int:
    result = lab.api("core/view/messages", start="0", count="10000")
    messages = result.get("messages")
    assert isinstance(messages, list), result
    return sum(1 for m in messages if isinstance(m, dict) and str(m.get("type")) == OAST_TYPE)


def _measure(cli: LabCli, lab: OastLab, enabled: bool, evidence: dict[str, object]) -> OastScanLab:
    out = OastScanLab(enabled=enabled)
    up = lab.stack_up("crapi")
    assert up.code == 0, up.stdout[-500:]
    evidence["stack_run_id"] = up.data.get("run_id")
    lab.start(synthetic=False, configure=False)
    lab.attach_workshop()
    lab.topology(workshop=True)
    out.interactions_before = lab.interaction_count()
    started = time.monotonic()
    probe = cli.run("probe", "crapi", "--only", OPERATION, timeout=900)
    out.seconds["probe"] = round(time.monotonic() - started, 1)
    out.exit_codes["probe"] = probe.code
    assert probe.code == 0, probe.stdout[-800:]
    out.run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run(
        "scan", "crapi", "--run", out.run_id, "--only", OPERATION, "--max-minutes", "6",
        timeout=1200,
    )  # fmt: skip
    out.seconds["scan"] = round(time.monotonic() - started, 1)
    out.exit_codes["scan"] = done.code
    assert done.code in {0, 3}, done.stdout[-800:]
    report = cli.run("report", "crapi", "--run", out.run_id)
    out.exit_codes["report"] = report.code
    assert report.code in {0, 1}, report.stdout[-500:]
    run_dir = cli.runs / out.run_id
    out.scan = json.loads((run_dir / "scan.json").read_text(encoding="utf-8"))
    data = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    out.findings = list(data.get("findings", []))
    out.interactions_after = lab.interaction_count()
    out.oast_messages = _oast_messages(lab)
    out.proxy_rows = len(proxy_audit(cli))
    lab.assert_no_external_route()
    evidence["external"] = "ENETUNREACH"
    return out


@pytest.fixture(scope="module", params=[True, False], ids=["key_on", "key_off"])
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[OastScanLab]:
    require_docker()
    enabled: bool = request.param
    key = secrets.token_hex(32)
    token = secrets.token_hex(8)
    extra = {
        "HDAST_ZAP_API_KEY": key,
        "CRAPI_DB_PASSWORD": secrets.token_hex(16),
        "CRAPI_USER_A_EMAIL": f"a.{token}@example.com",
        "CRAPI_USER_B_EMAIL": f"b.{token}@example.com",
        "CRAPI_USER_A_PASSWORD": "Aa1#" + secrets.token_hex(16),
        "CRAPI_USER_B_PASSWORD": "Aa1#" + secrets.token_hex(16),
    }
    cli = LabCli(tmp_path_factory.mktemp("oast-scan"), extra)
    for name in tuple(cli.env):
        if name.startswith("CRAPI_") and name not in extra:
            del cli.env[name]
    cli.install_product(
        "crapi", REPO / "lab/crapi/product-profile", (REPO / "lab/crapi/openapi.json",)
    )
    _tweak_profile(cli.products / "crapi", oast=enabled)
    marker = "lab-" + secrets.token_hex(6)
    probe = OastLab(cli, key, secrets.token_hex(6))
    probe.assert_project_unused()
    probe.assert_crapi_unused()
    evidence: dict[str, object] = {
        "marker": marker,
        "source": "crapi-scan",
        "oast": enabled,
        "interaction": "not_confirmed",
    }
    try:
        measured = _measure(cli, probe, enabled, evidence)
        ssrf = measured.scan.get("ssrf") or {}
        evidence.update(
            {
                "run_id": measured.run_id,
                "seconds": measured.seconds,
                "interactions": [measured.interactions_before, measured.interactions_after],
                "mensagens_oast_no_zap": measured.oast_messages,
                "ssrf_pedidos": ssrf.get("sent"),
                "ssrf_retornos": ssrf.get("observed"),
                "ssrf_planejados": ssrf.get("planned"),
                "pedidos_no_proxy": measured.proxy_rows,
                "achados_oast": len(_oast_findings(measured)),
                "exit_codes": measured.exit_codes,
            }
        )
        yield measured
    finally:
        finish_proof(probe, marker, evidence)
        record_metrics(f"lab-oast-scan-{'on' if enabled else 'off'}", evidence)


def _oast_findings(item: OastScanLab) -> list[dict[str, Any]]:
    ids = {OAST_PLUGIN, "40043", "90023", "90036"}
    return [f for f in item.findings if str(f.get("plugin_id")) in ids]


def test_with_the_key_on_the_return_is_observed_and_becomes_an_ssrf_finding(
    lab: OastScanLab,
) -> None:
    if not lab.enabled:
        pytest.skip("só vale com scan.oast ligado")
    found = [f for f in lab.findings if f.get("plugin_id") == OAST_PLUGIN]
    assert found, "o retorno do C11 não virou achado de SSRF"
    assert found[0]["operation_id"] == OPERATION
    assert found[0]["parameter"] == FIELD
    assert found[0]["classification"]["cwe"] == 918
    assert "Evento OAST" in found[0]["evidence"]["zap_evidence"]
    ssrf = lab.scan["ssrf"]
    assert ssrf["observed"] >= 1
    assert 1 <= ssrf["sent"] <= ssrf["cap"] == 10
    assert lab.scan["policy"]["oast"] is True
    assert lab.interactions_after > lab.interactions_before
    assert lab.oast_messages >= 1


def test_with_the_key_off_there_is_no_oast_traffic_and_no_oast_finding(lab: OastScanLab) -> None:
    if lab.enabled:
        pytest.skip("só vale com scan.oast desligado")
    assert lab.interactions_before == lab.interactions_after == 0
    assert lab.oast_messages == 0
    assert lab.scan.get("ssrf") is None
    assert lab.scan["policy"]["oast"] is False
    assert lab.scan["policy"]["oast_rules"] == []
    assert _oast_findings(lab) == []
