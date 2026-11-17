"""Injeção em cabeçalhos (V1.12, F6, ADR 0097): H11 da Clínica Piloto, só no laboratório.

Nível RÁPIDO: uma pilha por modo, `probe` completo e um `scan --only buscarMedicoPorCabecalho`
(a operação da H11, `X-CRM`). O papel da carta é feito na CÓPIA descartável do perfil, que ganha
`scan.inject_headers: true`. Provas:

- vulnerável, chave ligada: o ZAP acusa injeção de SQL nessa operação (H11 achada);
- vulnerável, chave desligada: não acusa (a política de hoje não alcança o cabeçalho);
- seguro, chave ligada: não acusa.

Medidas (não asserções): pedidos da varredura ativa da operação com e sem a chave (soma de
`requests` do `rule-stats.json`) e duração. Vão para `HDAST_IT_METRICS_DIR/lab-header-injection-*`.
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.lab_support import PILOT_PROFILE, LabCli, proxy_audit, require_docker
from tests.integration.run_support import record_metrics, throwaway_pilot_env

pytestmark = [pytest.mark.integration, pytest.mark.lab_fast]

OPERATION = "buscarMedicoPorCabecalho"
HEADER = "X-CRM"
SQL_TITLE = "sql injection"
# (modo, chave ligada): o perfil muda a impressão digital do proxy, então cada cenário tem a sua
# pilha, com a chave já no perfil antes do `stack up`.
SCENARIOS = (("vulnerable", True), ("vulnerable", False), ("secure", True))


@dataclass
class HeaderLab:
    """O que um modo produziu: achados e pedidos da operação, sem e com a chave."""

    mode: str
    enabled: bool
    run_id: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    mask: int = 0
    header_rows: int = 0
    exit_code: int = -1
    seconds: dict[str, float] = field(default_factory=dict)


def _set_inject_headers(target: Path, enabled: bool) -> None:
    """Liga ou desliga o campo só na CÓPIA descartável do perfil (faz o papel da carta)."""
    profile = yaml.safe_load(target.read_text(encoding="utf-8"))
    scan = profile.setdefault("scan", {})
    if enabled:
        scan["inject_headers"] = True
    else:
        scan.pop("inject_headers", None)
    target.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")


def _sql_findings(cli: LabCli, run_id: str) -> list[dict[str, Any]]:
    data = json.loads((cli.runs / run_id / "findings.json").read_text(encoding="utf-8"))
    return [
        item
        for item in data.get("findings", [])
        if item.get("operation_id") == OPERATION and SQL_TITLE in str(item.get("title", "")).lower()
    ]


def _operation_requests(cli: LabCli, run_id: str) -> int:
    stats = json.loads((cli.runs / run_id / "rule-stats.json").read_text(encoding="utf-8"))
    rules = [r for op in stats["operations"] if op["operation_id"] == OPERATION for r in op["rules"]]
    return sum(int(rule.get("requests", 0)) for rule in rules)


def _measure(cli: LabCli, mode: str, enabled: bool) -> HeaderLab:
    seconds: dict[str, float] = {}
    _set_inject_headers(cli.products / "clinica-piloto" / "target.yml", enabled)
    flags = ["--secure"] if mode == "secure" else []
    started = time.monotonic()
    up = cli.run("stack", "up", "clinica-piloto", "--build", *flags, timeout=900)
    assert up.code == 0, up.stdout[-500:]
    seconds["stack_up_build"] = round(time.monotonic() - started, 1)
    assert cli.run("preflight", "clinica-piloto").code == 0
    started = time.monotonic()
    probe = cli.run("probe", "clinica-piloto", timeout=900)
    seconds["probe"] = round(time.monotonic() - started, 1)
    assert probe.code == 0, probe.stdout[-800:]
    run_id = str(probe.envelope["run_id"])
    started = time.monotonic()
    done = cli.run(
        "scan", "clinica-piloto", "--run", run_id,
        "--max-minutes", "6", "--only", OPERATION, timeout=1200,
    )  # fmt: skip
    seconds["scan"] = round(time.monotonic() - started, 1)
    assert done.code in {0, 3}, done.stdout[-800:]
    report = cli.run("report", "clinica-piloto", "--run", run_id)
    assert report.code in {0, 1}, report.stdout[-500:]
    scan = json.loads((cli.runs / run_id / "scan.json").read_text(encoding="utf-8"))
    rows = [r for r in proxy_audit(cli) if r["path"].startswith("/api/medicos/por-cabecalho")]
    return HeaderLab(
        mode=mode,
        enabled=enabled,
        run_id=run_id,
        findings=_sql_findings(cli, run_id),
        requests=_operation_requests(cli, run_id),
        mask=int(scan["policy"]["injectable_mask"]),
        header_rows=len(rows),
        exit_code=done.code,
        seconds=seconds,
    )


@pytest.fixture(scope="module", params=SCENARIOS, ids=lambda p: f"{p[0]}-{'on' if p[1] else 'off'}")
def lab(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[HeaderLab]:
    require_docker()
    mode, enabled = request.param
    cli = LabCli(tmp_path_factory.mktemp(f"header-{mode}"), throwaway_pilot_env())
    cli.install_product("clinica-piloto", PILOT_PROFILE)
    try:
        measured = _measure(cli, mode, enabled)
        key = "on" if enabled else "off"
        record_metrics(
            f"lab-header-injection-{mode}-{key}",
            {
                "run_id": measured.run_id,
                "seconds": measured.seconds,
                "mask": measured.mask,
                "pedidos_da_operacao": measured.requests,
                "pedidos_no_proxy": measured.header_rows,
                "achados_sql": len(measured.findings),
                "exit_code": measured.exit_code,
            },
        )
        yield measured
    finally:
        cli.stack_down()


def test_with_the_key_on_the_vulnerable_clinic_reports_sql_injection_in_the_header(
    lab: HeaderLab,
) -> None:
    if (lab.mode, lab.enabled) != ("vulnerable", True):
        pytest.skip("só vale no cenário vulnerável com a chave ligada")
    assert lab.mask == 35 + 16 + 4 + 8
    assert lab.findings, "H11 (X-CRM) não foi achada com scan.inject_headers"
    assert {str(item.get("parameter")).lower() for item in lab.findings} == {HEADER.lower()}


def test_with_the_key_off_the_vulnerable_clinic_does_not_report_the_header_injection(
    lab: HeaderLab,
) -> None:
    if (lab.mode, lab.enabled) != ("vulnerable", False):
        pytest.skip("só vale no cenário vulnerável com a chave desligada")
    assert lab.mask == 35 + 16
    assert lab.findings == []


def test_with_the_key_on_the_secure_clinic_does_not_report_the_header_injection(
    lab: HeaderLab,
) -> None:
    if (lab.mode, lab.enabled) != ("secure", True):
        pytest.skip("só vale no cenário seguro com a chave ligada")
    assert lab.mask == 35 + 16 + 4 + 8
    assert lab.findings == []
