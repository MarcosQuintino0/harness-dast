"""F5 e F8 (ADR 0101 e 0102): limite de consumo e inventário provados no laboratório local.

- crAPI: escopo mínimo da cópia descartável com OTP v2 e v3 (C3), a lista de posts (paginável) e
  os `GET` do inventário; chaves LIGADAS numa execução e DESLIGADAS noutra, na mesma pilha.
- Clínica Piloto no modo seguro: as duas chaves ligadas; o resultado honesto vai para as medidas.

Use `HDAST_IT_STACK_SUFFIX` para isolar as pilhas e `HDAST_IT_METRICS_DIR` para as medidas.
Aprovação descartável do suporte de teste; nunca a pasta de estado real.
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.domain.inventory_checks import DOC_PATHS
from tests.integration.lab_support import (
    PILOT_PROFILE,
    REPO,
    LabCli,
    read_jsonl,
    require_docker,
)
from tests.integration.run_support import record_metrics, throwaway_pilot_env
from tests.integration.v112_proof_support import prepare_control_product

pytestmark = pytest.mark.integration

OTP_PATHS = ("/identity/api/auth/v2/check-otp", "/identity/api/auth/v3/check-otp")
POSTS = "/community/api/v2/community/posts/recent"
CRAPI_ONLY = ("get_recent_posts", "check_otp_v2", "check_otp_v3")


def _crapi_product(products: Path, *, enabled: bool) -> None:
    """Produto descartável: controle, OTP v2 e v3, posts e `GET` do inventário (papel da carta)."""
    prepare_control_product(products)
    product = products / "crapi"
    spec_path = product / "openapi.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    full = json.loads((REPO / "lab/crapi/openapi.json").read_text(encoding="utf-8"))
    for path in (*OTP_PATHS, POSTS):
        spec["paths"][path] = full["paths"][path]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    set_flags(product / "target.yml", enabled=enabled, extra_scope=True)


def set_flags(target: Path, *, enabled: bool, extra_scope: bool = False) -> None:
    """Liga ou desliga as duas chaves (papel da carta) e, se pedido, abre o escopo mínimo."""
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if extra_scope:
        base = data["scope"]["allow"][0]
        data["scope"]["allow"] += [
            dict(base, paths=list(OTP_PATHS), methods=["POST"]),
            dict(base, paths=[POSTS, "/identity/api/auth/**", *DOC_PATHS], methods=["GET"]),
        ]
        data["scope"]["deny_paths"] = [
            item for item in data["scope"].get("deny_paths", []) if "check-otp" not in item
        ]
    if enabled:
        data["extra_checks"] = {"allow_rate_tests": True, "inventory": True}
    else:
        data.pop("extra_checks", None)
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _run_cycle(cli: LabCli, product: str, only: tuple[str, ...]) -> dict[str, Any]:
    """`probe` e `scan` dirigidos; devolve o `run_id`, o `scan.json` e as contagens da auditoria."""
    flags = [item for name in only for item in ("--only", name)]
    probe = cli.run("probe", product, *flags, timeout=900)
    assert probe.code == 0, probe.stdout[-600:]
    run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run("scan", product, "--run", run_id, *flags, "--max-minutes", "8", timeout=1200)
    seconds = round(time.monotonic() - started, 1)
    assert done.code in {0, 3}, done.stdout[-800:]
    report = cli.run("report", product, "--run", run_id)
    assert report.code in {0, 1}, report.stdout[-500:]
    run_dir = cli.runs / run_id
    scan = json.loads((run_dir / "scan.json").read_text(encoding="utf-8"))
    findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    audit = read_jsonl(run_dir / "audit.jsonl")
    prefixes: dict[str, int] = {}
    for row in audit:
        name = str(row.get("operation_id", ""))
        for prefix in ("rate:", "inventory:"):
            if name.startswith(prefix):
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
    return {
        "run_id": run_id,
        "scan_seconds": seconds,
        "scan": scan,
        "findings": findings.get("findings", []),
        "audit_rows": prefixes,
    }


def _summary(cycle: dict[str, Any]) -> dict[str, Any]:
    scan = cycle["scan"]
    return {
        "run_id": cycle["run_id"],
        "scan_seconds": cycle["scan_seconds"],
        "scan_status": scan["status"],
        "audit_rows": cycle["audit_rows"],
        "rate": scan.get("rate_checks"),
        "inventory": scan.get("inventory"),
        "findings": [
            {
                key: f.get(key)
                for key in ("plugin_id", "operation_id", "proposed_severity", "parameter")
            }
            for f in cycle["findings"]
            if str(f.get("plugin_id", "")).startswith("hdast-")
        ],
    }


def test_crapi_limite_de_consumo_e_inventario_com_e_sem_as_chaves(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, {})
    for key in tuple(cli.env):
        if key.startswith("CRAPI_"):
            del cli.env[key]
    _crapi_product(cli.products, enabled=True)
    records: dict[str, Any] = {}
    try:
        assert cli.run("stack", "up", "crapi", timeout=600).code == 0
        assert cli.run("preflight", "crapi").code == 0
        on = _run_cycle(cli, "crapi", CRAPI_ONLY)
        records["on"] = _summary(on)
        rate = on["scan"]["rate_checks"]
        inventory = on["scan"]["inventory"]
        assert rate is not None
        assert inventory is not None
        assert rate["sent"] <= rate["cap"]
        assert inventory["sent"] <= inventory["cap"]
        attempts = {r["subject"]: r for r in rate["results"] if r["check"] == "attempts"}
        # O crAPI responde 500 a OTP errado, mesmo com dígitos do tamanho do contrato: não é
        # rejeição de credencial. A checagem fica inconclusiva, sem achado (ADR 0101, correção da
        # validação independente); antes ela achava o C3 por 20 respostas 500 iguais.
        for subject in ("check_otp_v2", "check_otp_v3"):
            assert attempts[subject]["outcome"] == "inconclusive", rate
            assert attempts[subject]["detail"] == "server_error_http_500", rate
            assert attempts[subject]["requests"] == 1
        assert on["audit_rows"].get("rate:", 0) >= 4
        found = [f for f in on["findings"] if f.get("plugin_id") == "hdast-rate-attempts"]
        assert found == []

        # Mudar o perfil muda a aprovação: o proxy de escopo exige pilha nova.
        cli.stack_down()
        set_flags(cli.products / "crapi" / "target.yml", enabled=False)
        assert cli.run("stack", "up", "crapi", timeout=600).code == 0
        # O `probe` do OTP (que responde 500) deixa a intenção no diário e não se repete às cegas:
        # a execução sem as chaves usa só a lista de posts, e nenhum pedido de checagem sai.
        off = _run_cycle(cli, "crapi", CRAPI_ONLY[:1])
        records["off"] = _summary(off)
        assert off["scan"].get("rate_checks") is None
        assert off["scan"].get("inventory") is None
        assert off["audit_rows"] == {}
        assert not [f for f in off["findings"] if str(f.get("plugin_id", "")).startswith("hdast-")]
    finally:
        record_metrics("v112-f5-f8-crapi", records)
        cli.stack_down()


def test_clinica_piloto_no_modo_seguro_com_as_duas_chaves(tmp_path: Path) -> None:
    require_docker()
    cli = LabCli(tmp_path, throwaway_pilot_env())
    product = cli.install_product("clinica-piloto", PILOT_PROFILE)
    set_flags(product / "target.yml", enabled=True)
    records: dict[str, Any] = {}
    try:
        assert cli.run("stack", "up", "clinica-piloto", "--secure", timeout=900).code == 0
        assert cli.run("preflight", "clinica-piloto").code == 0
        cycle = _run_cycle(cli, "clinica-piloto", ("listarPacientes", "listarConvenios"))
        records.update(_summary(cycle))
        rate = cycle["scan"]["rate_checks"]
        inventory = cycle["scan"]["inventory"]
        assert rate is not None
        assert inventory is not None
        assert rate["sent"] <= rate["cap"]
        assert inventory["sent"] <= inventory["cap"]
        assert not [
            f for f in records["findings"] if f["proposed_severity"] in {"high", "critical"}
        ]
    finally:
        record_metrics("v112-f5-f8-clinica-segura", records)
        cli.stack_down()
