"""Cenários prontos para testar o painel da execução (`PanelSources`), sem arquivo nem rede."""

from datetime import UTC, date, timedelta, timezone
from typing import Any

from harness_dast.domain.api_model import Operation
from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.panel.sources import PanelSources
from harness_dast.domain.report.build import assemble_report
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run_summary import RunOptions, RunSummary, StageRecord
from harness_dast.domain.scan_plan import ScanSkip
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report.helpers import (
    RUN_ID,
    entry,
    operation,
    probe_result,
    scan_result,
)

ZONE = timezone(timedelta(hours=-3))
PRODUCT = "vampi"
XSS = "<script>alert(1)</script><img src=x onerror=alert(1)>\"'&"
BIDI = "‮evil‬"


def spec_operations(
    summary: str | None = "Ver usuário", tag: str | None = "Usuários"
) -> tuple[Operation, ...]:
    """Operações do OpenAPI do cenário: uma atacada, uma que cria, uma que apaga e duas mais."""
    tags = (tag,) if tag else ()
    return (
        Operation(
            operation_id="obter",
            method="get",
            path="/users/v1/{username}",
            tags=tags,
            summary=summary,
        ),
        Operation(operation_id="criar", method="post", path="/users/v1"),
        Operation(operation_id="apagar", method="delete", path="/users/v1/{username}"),
        Operation(operation_id="listar", method="get", path="/users/v1"),
        Operation(operation_id="nova", method="get", path="/nova"),
    )


def findings_report(alerts: list[dict[str, str]] | None = None) -> FindingsReport:
    """`findings.json` com um achado grave ligado à operação `obter`."""
    ops = [
        operation("obter", "GET", "/users/v1/{username}"),
        operation("criar", "POST", "/users/v1"),
        operation("apagar", "DELETE", "/users/v1/{username}", "skipped_destructive"),
        operation("listar", "GET", "/users/v1", "validation_error"),
    ]
    return assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))]),
        raw_alerts=alerts if alerts is not None else [zap_alert("9")],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=("Authorization", "Bearer $TOKEN"),
        csrf_header=None,
    )


def run_summary(**changes: Any) -> RunSummary:
    """`run.json` de um `hdast run` que terminou, com o tempo de cada etapa."""
    stages = (
        StageRecord(name="preflight", status="ok", duration_seconds=70.0),
        StageRecord(name="probe", status="ok", duration_seconds=20.0),
        StageRecord(name="scan", status="ok", duration_seconds=1140.0),
        StageRecord(name="authz", status="skipped", duration_seconds=0.0),
        StageRecord(name="negative", status="skipped", duration_seconds=0.0),
        StageRecord(name="report", status="ok", duration_seconds=2.0),
    )
    base: dict[str, Any] = {
        "product": PRODUCT,
        "run_id": RUN_ID,
        "status": "completed",
        "exit_code": 0,
        "started_at": "2026-11-13T23:08:00+00:00",
        "finished_at": "2026-11-13T23:36:00+00:00",
        "duration_seconds": 1680.0,
        "options": RunOptions(),
        "stages": stages,
    }
    base.update(changes)
    return RunSummary(**base)


def sources(**changes: Any) -> PanelSources:
    """Cenário completo e feliz: perfil, OpenAPI, probe, scan, achados e `run.json`."""
    ops = spec_operations()
    probe = probe_result(
        [
            operation("obter", "GET", "/users/v1/{username}"),
            operation("criar", "POST", "/users/v1"),
            operation("apagar", "DELETE", "/users/v1/{username}", "skipped_destructive"),
            operation("listar", "GET", "/users/v1", "validation_error"),
        ]
    )
    scan = scan_result(
        [entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))],
        skipped=[
            ScanSkip(
                operation_id="criar",
                method="POST",
                path="/users/v1",
                reason="mutating",
                message="x",
            )
        ],
    )
    base: dict[str, Any] = {
        "product": PRODUCT,
        "run_id": RUN_ID,
        "timezone": ZONE,
        "summary": run_summary(),
        "probe": probe,
        "scan": scan,
        "findings": findings_report(),
        "operations": ops,
        "fence_mode": "strict",
        "authorization_reference": "CHG-4821",
        "authorization_valid_until": date(2999, 12, 31),
    }
    base.update(changes)
    return PanelSources(**base)


def view(**changes: Any) -> PanelView:
    """Visão montada do cenário feliz (com as mudanças pedidas nas fontes)."""
    return build_panel_view(sources(**changes))


def bare() -> PanelSources:
    """Só o mínimo: nenhum arquivo, nenhuma fonte opcional."""
    return PanelSources(product=PRODUCT, run_id=RUN_ID, timezone=UTC)
