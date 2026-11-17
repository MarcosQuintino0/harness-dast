"""Regressão de cobertura executada por regra."""

import pytest

from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.rule_stats import OperationRules, RuleStat
from harness_dast.domain.scan_rule_coverage import rule_coverage_gaps
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result


def test_regra_pulada_com_progresso_100_torna_relatorio_parcial() -> None:
    from harness_dast.domain.panel.build import build_panel_view
    from harness_dast.domain.panel.coverage import render_coverage
    from tests.unit.domain.panel.helpers import sources

    item = entry("obter", "GET", "/items", 1).model_copy(update={"scan_id": "1"})
    rules = OperationRules(
        operation_id="obter",
        scan_id="1",
        rules=(
            RuleStat(plugin_id=40026, name="DOM", state="skipped", skip_reason="max_rule_time"),
        ),
    )
    gaps = rule_coverage_gaps((item,), (rules,))
    scan = scan_result([item]).model_copy(update={"rule_coverage_gaps": gaps})
    report = assemble_report(
        probe=probe_result([operation("obter", "GET", "/items")]),
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

    assert item.outcome == "completed"
    assert item.progress == 100
    assert report.coverage.partial
    assert gaps[0].plugin_id == 40026
    assert gaps[0].reason == "max_rule_time"
    for text in (render_markdown(report), render_html(report)):
        assert "40026" in text
        assert "skipped" in text
        assert "obter" in text
    panel = render_coverage(
        build_panel_view(
            sources(probe=probe_result([operation("obter", "GET", "/items")]), scan=scan)
        )
    )
    assert "Cobertura parcial" in panel
    assert "Nada ficou de fora dentro do que a carta permite" not in panel


@pytest.mark.parametrize("state", ["interrupted", "pending", "unknown", "skipped"])
def test_estados_incompletos_geram_lacuna(state: str) -> None:
    item = entry("obter", "GET", "/items", 1).model_copy(update={"scan_id": "1"})
    rule = RuleStat.model_validate({"plugin_id": 1, "name": "x", "state": state})
    gaps = rule_coverage_gaps(
        (item,), (OperationRules(operation_id="obter", scan_id="1", rules=(rule,)),)
    )
    assert len(gaps) == 1
    assert gaps[0].state == state


def test_estatistica_ausente_ou_vazia_e_lacuna_e_texto_externo_nao_vaza() -> None:
    item = entry("obter", "GET", "/items", 1).model_copy(update={"scan_id": "1"})
    for stats in (
        (),
        (OperationRules(operation_id="obter", scan_id="1"),),
        (OperationRules(operation_id="obter", scan_id="1", unavailable_reason="texto externo"),),
    ):
        gaps = rule_coverage_gaps((item,), stats)
        assert gaps[0].state == "unavailable"
        assert "texto externo" not in gaps[0].model_dump_json()


def test_regras_completas_nao_criam_lacuna() -> None:
    item = entry("obter", "GET", "/items", 1).model_copy(update={"scan_id": "1"})
    rules = OperationRules(
        operation_id="obter",
        scan_id="1",
        rules=(RuleStat(plugin_id=1, name="x", state="completed"),),
    )
    assert rule_coverage_gaps((item,), (rules,)) == ()


def test_legado_nao_prova_cobertura_completa() -> None:
    item = entry("obter", "GET", "/items", 1).model_copy(update={"scan_id": "1"})
    report = assemble_report(
        probe=probe_result([operation("obter", "GET", "/items")]),
        scan=scan_result([item]),
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
    assert report.coverage.rule_coverage_gaps is None
    assert "Cobertura por regra indisponível" in render_markdown(report)
