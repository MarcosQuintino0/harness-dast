"""Recomendações para lacunas de cobertura e recusas do proxy."""

import pytest

from harness_dast.domain.report_actions import next_steps
from harness_dast.domain.scan_result import RuleCoverageGap
from harness_dast.domain.traffic import TrafficSummary
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.test_report_html import report


@pytest.mark.parametrize(
    ("status", "gaps"),
    [
        (
            "completed",
            (
                RuleCoverageGap(
                    operation_id="obter", plugin_id=40026, state="skipped", reason="other"
                ),
            ),
        ),
        ("completed", None),
        ("stopped_deadline", ()),
    ],
)
def test_cobertura_parcial_nao_inventa_parada(status: str, gaps: object) -> None:
    base = report([])
    coverage = base.coverage.model_copy(
        update={
            "partial": True,
            "scan_status": status,
            "rule_coverage_gaps": gaps,
        }
    )

    step = next_steps(base.model_copy(update={"coverage": coverage}))[0]

    assert "cobertura tem lacunas ou não pôde ser comprovada" in step
    assert "parou antes do fim" not in step
    assert "após tratar a causa" in step
    assert "sem ampliar escopo, limites nem janela sem nova autorização" in step


@pytest.mark.parametrize(
    ("reasons", "expected_note"),
    [
        ({"rate_backoff": 2}, "Desses, 2 foram recusados durante o recuo temporário."),
        ({"deny_path": 2}, ""),
        (
            {"rate_backoff": 1, "deny_path": 1},
            "Desses, 1 foram recusados durante o recuo temporário.",
        ),
        ({}, ""),
    ],
)
def test_recusas_do_proxy_distinguem_recuo_sem_inventar_motivo(
    reasons: dict[str, int], expected_note: str
) -> None:
    base = report([])
    coverage = base.coverage.model_copy(
        update={
            "traffic": TrafficSummary(enabled=True, denied=2, denied_by_reason=reasons),
        }
    )

    steps = next_steps(base.model_copy(update={"coverage": coverage}))
    step = next(item for item in steps if item.startswith("O proxy recusou"))

    assert "O proxy recusou 2 pedido(s)" in step
    assert "A cerca de escopo recusou" not in step
    if expected_note:
        assert expected_note in step
    else:
        assert "Desses," not in step
    assert "seção de tráfego recusado" in step


def test_gravidade_desconhecida_continua_destacada() -> None:
    alert = zap_alert("9", risk="Unknown")
    steps = next_steps(report([alert]))

    assert any("gravidade desconhecida" in step for step in steps)
