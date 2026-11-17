"""Regras alpha/beta selecionadas (V1.12, F7, ADR 0103): C12 do crAPI e controle seguro da Clínica.

Nível RÁPIDO. O papel da carta é feito na CÓPIA descartável do perfil, que ganha
`extra_checks.experimental_rules: true` (cenário ligado). Provas:

- crAPI, ligado: escopo mínimo com a operação do C12 (`validate_coupon`, campo `coupon_code`); as
  regras de NoSQL rodam (`rule-stats.json`) e o resultado é registrado, achado ou não;
- crAPI, desligado: nenhuma regra experimental roda e nenhum achado sai marcado;
- Clínica Piloto no modo SEGURO, ligado: conta os alarmes das regras experimentais (todo achado
  marcado `experimental` ali é alarme falso, porque o modo seguro não tem a falha).

Medidas (não asserções sobre o achado) vão para `HDAST_IT_METRICS_DIR/lab-experimental-*`.
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import PILOT_PROFILE, REPO, LabCli, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.v112_proof_support import prepare_control_product

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

OPERATION = "validate_coupon"
COUPON_PATH = "/community/api/v2/coupon/validate-coupon"
EXPERIMENTAL_IDS = {40033, 90039, 40046}


@dataclass
class ExperimentalLab:
    """O que um cenário produziu."""

    name: str
    enabled: bool
    run_id: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    experimental: list[dict[str, Any]] = field(default_factory=list)
    experimental_requests: int = 0
    experimental_rules_seen: list[int] = field(default_factory=list)
    exit_code: int = -1
    seconds: dict[str, float] = field(default_factory=dict)


def _set_key(target: Path, enabled: bool) -> None:
    """Liga ou desliga a chave só na CÓPIA descartável do perfil (faz o papel da carta)."""
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if enabled:
        data["extra_checks"] = {"experimental_rules": True}
    else:
        data.pop("extra_checks", None)
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _prepare_crapi(products: Path, enabled: bool) -> None:
    """Produto de controle mais a operação do C12 e a regra de dados do cupom do laboratório."""
    prepare_control_product(products)
    product = products / "crapi"
    spec_path = product / "openapi.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    full = json.loads((REPO / "lab/crapi/openapi.json").read_text(encoding="utf-8"))
    spec["paths"][COUPON_PATH] = {"post": full["paths"][COUPON_PATH]["post"]}
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    rules = yaml.safe_load(
        (REPO / "lab/crapi/product-profile/data-rules.yml").read_text(encoding="utf-8")
    )
    rules["rules"] = [rule for rule in rules["rules"] if rule["match"]["operation"] == OPERATION]
    (product / "data-rules.yml").write_text(
        yaml.safe_dump(rules, sort_keys=False), encoding="utf-8"
    )
    target = product / "target.yml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data["scope"]["allow"].append(
        dict(data["scope"]["allow"][0], paths=[COUPON_PATH], methods=["POST"])
    )
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    _set_key(target, enabled)


def _experimental_rules(cli: LabCli, run_id: str) -> tuple[int, list[int]]:
    stats = json.loads((cli.runs / run_id / "rule-stats.json").read_text(encoding="utf-8"))
    rules = [
        rule
        for op in stats["operations"]
        for rule in op["rules"]
        if int(rule["plugin_id"]) in EXPERIMENTAL_IDS
    ]
    return (
        sum(int(rule.get("requests", 0)) for rule in rules),
        sorted({int(rule["plugin_id"]) for rule in rules}),
    )


def _collect(cli: LabCli, name: str, enabled: bool, run_id: str, code: int) -> ExperimentalLab:
    run_dir = cli.runs / run_id
    scan = json.loads((run_dir / "scan.json").read_text(encoding="utf-8"))
    data = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    requests, seen = _experimental_rules(cli, run_id)
    findings = list(data.get("findings", []))
    return ExperimentalLab(
        name=name,
        enabled=enabled,
        run_id=run_id,
        policy=scan["policy"],
        findings=findings,
        experimental=[item for item in findings if item.get("experimental")],
        experimental_requests=requests,
        experimental_rules_seen=seen,
        exit_code=code,
    )


def _crapi(cli: LabCli, enabled: bool) -> ExperimentalLab:
    seconds: dict[str, float] = {}
    started = time.monotonic()
    assert cli.run("stack", "up", "crapi", timeout=900).code == 0
    seconds["stack_up"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "crapi").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "crapi", "--only", OPERATION, timeout=900)
    seconds["probe"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run(
        "scan", "crapi", "--run", run_id, "--only", OPERATION, "--max-minutes", "8", timeout=1500
    )
    seconds["scan"] = round(time.monotonic() - started, 1)
    assert done.code in {0, 3}, done.stdout[-800:]
    assert cli.run("report", "crapi", "--run", run_id).code in {0, 1}
    lab = _collect(cli, "crapi", enabled, run_id, done.code)
    lab.seconds = seconds
    return lab


def _clinic(cli: LabCli, enabled: bool) -> ExperimentalLab:
    seconds: dict[str, float] = {}
    _set_key(cli.products / "clinica-piloto" / "target.yml", enabled)
    started = time.monotonic()
    up = cli.run("stack", "up", "clinica-piloto", "--build", "--secure", timeout=900)
    assert up.code == 0, up.stdout[-500:]
    seconds["stack_up_build"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    seconds["probe"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run("scan", "clinica-piloto", "--run", run_id, "--max-minutes", "12", timeout=1800)
    seconds["scan"] = round(time.monotonic() - started, 1)
    assert done.code in {0, 3}, done.stdout[-800:]
    assert cli.run("report", "clinica-piloto", "--run", run_id).code in {0, 1}
    lab = _collect(cli, "clinica-segura", enabled, run_id, done.code)
    lab.seconds = seconds
    return lab


SCENARIOS = (("crapi", True), ("crapi", False), ("clinica", True))


@pytest.fixture(scope="module", params=SCENARIOS, ids=lambda p: f"{p[0]}-{'on' if p[1] else 'off'}")
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[ExperimentalLab]:
    require_docker()
    kind, enabled = request.param
    if kind == "crapi":
        cli = LabCli(tmp_path_factory.mktemp("experimental-crapi"), {})
        for key in tuple(cli.env):
            if key.startswith("CRAPI_"):
                del cli.env[key]
        _prepare_crapi(cli.products, enabled)
    else:
        cli = LabCli(tmp_path_factory.mktemp("experimental-clinic"), throwaway_pilot_env())
        cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        measured = _crapi(cli, enabled) if kind == "crapi" else _clinic(cli, enabled)
        record_metrics(
            f"lab-experimental-{kind}-{'on' if enabled else 'off'}",
            {
                "run_id": measured.run_id,
                "seconds": measured.seconds,
                "exit_code": measured.exit_code,
                "achados_total": len(measured.findings),
                "achados_experimentais": [
                    {k: f[k] for k in ("plugin_id", "title", "operation_id", "proposed_severity")}
                    for f in measured.experimental
                ],
                "pedidos_das_regras_experimentais": measured.experimental_requests,
                "regras_experimentais_vistas": measured.experimental_rules_seen,
                "regras_ligadas": measured.policy.get("experimental_rules"),
            },
        )
        yield measured
    finally:
        cli.stack_down()


def test_crapi_with_the_key_on_runs_the_nosql_rules_and_records_the_result(
    lab: ExperimentalLab,
) -> None:
    if (lab.name, lab.enabled) != ("crapi", True):
        pytest.skip("só vale no crAPI com a chave ligada")
    assert lab.policy["experimental_rules"] == [40033, 90039]
    assert {40033, 90039} <= set(lab.experimental_rules_seen)
    assert lab.experimental_requests > 0
    # O resultado (achado ou não) é medido, não afirmado: veja as métricas do cenário.
    assert all(item["experimental"] is True for item in lab.experimental)


def test_crapi_with_the_key_off_no_experimental_rule_runs(lab: ExperimentalLab) -> None:
    if (lab.name, lab.enabled) != ("crapi", False):
        pytest.skip("só vale no crAPI com a chave desligada")
    assert lab.policy["experimental_rules"] == []
    assert lab.experimental_requests == 0
    assert lab.experimental == []
    assert not any(str(item.get("plugin_id")) in {"40033", "90039"} for item in lab.findings)


def test_the_secure_clinic_with_the_key_on_counts_the_experimental_false_alarms(
    lab: ExperimentalLab,
) -> None:
    if (lab.name, lab.enabled) != ("clinica-segura", True):
        pytest.skip("só vale na Clínica segura com a chave ligada")
    assert lab.policy["experimental_rules"] == [40033, 90039]
    assert lab.experimental_requests > 0
    # No modo seguro não há falha NoSQL: todo achado experimental aqui é alarme falso. A contagem
    # vai para as métricas e para o ADR; o teste não a trava, para registrar o número como veio.
    assert all(item["experimental"] is True for item in lab.experimental)
