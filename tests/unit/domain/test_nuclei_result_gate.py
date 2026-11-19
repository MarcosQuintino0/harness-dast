"""`NucleiResult.reaches`: o gate de severidade conta os achados do Nuclei, não as tecnologias."""

import pytest

from harness_dast.domain.scan_config import FailOn
from tests.fakes.nuclei import nuclei_finding, nuclei_result


@pytest.mark.parametrize(
    ("severity", "threshold", "reaches"),
    [
        ("high", "high", True),
        ("critical", "high", True),
        ("medium", "high", False),
        ("medium", "medium", True),
        ("low", "medium", False),
        ("low", "low", True),
        ("info", "low", False),
        ("high", "none", False),
    ],
)
def test_alcanca_o_limiar_so_com_severidade_igual_ou_acima(
    severity: str, threshold: FailOn, reaches: bool
) -> None:
    result = nuclei_result(findings=(nuclei_finding(severity=severity),))

    assert result.reaches(threshold) is reaches


def test_sem_achados_nunca_alcanca_o_limiar() -> None:
    assert nuclei_result(findings=()).reaches("low") is False
