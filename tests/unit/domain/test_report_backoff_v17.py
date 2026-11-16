"""Recusa por recuo não pode parecer cobertura completa no relatório."""

import pytest

from harness_dast.domain.report_build import assemble_report, coverage_is_partial
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.traffic import TrafficSummary
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result


@pytest.mark.parametrize(("reason", "partial"), [("rate_backoff", True), ("deny_path", False)])
def test_recuo_distingue_lacuna_de_recusa_deliberada(reason: str, partial: bool) -> None:
    probe = probe_result([operation("list_items", "GET", "/items")])
    scan = scan_result([entry("list_items", "GET", "/items", 1)]).model_copy(
        update={
            "traffic": TrafficSummary(
                enabled=True, denied=1, denied_by_reason={reason: 1}, limit_rps=50
            )
        }
    )

    assert coverage_is_partial(probe, scan) is partial


def test_recuo_expoe_contagem_e_limite_de_atribuicao_nos_dois_formatos() -> None:
    probe = probe_result([operation("list_items", "GET", "/items")])
    scan = scan_result([entry("list_items", "GET", "/items", 1)]).model_copy(
        update={
            "traffic": TrafficSummary(
                enabled=True, denied=3, denied_by_reason={"rate_backoff": 3}, limit_rps=50
            )
        }
    )
    report = assemble_report(
        probe=probe,
        scan=scan,
        raw_alerts=[],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="t",
        harness_version="v",
        auth_header=None,
        csrf_header=None,
    )

    assert report.coverage.partial
    for rendered in (render_markdown(report), render_html(report)):
        text = rendered.replace("\\", "")
        assert "3 pedido(s) foram recusados durante o recuo" in text
        assert "contagem é global da etapa" in text
        assert "rate_backoff" in text
