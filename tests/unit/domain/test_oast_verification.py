"""Decisões conservadoras sobre o retorno fora de banda."""

import pytest

from harness_dast.domain.oast_verification import (
    OastVerification,
    combine_oast_availability,
    mark_ssrf_unobservable,
    oast_gap,
)
from tests.unit.domain.report.helpers import scan_result


@pytest.mark.parametrize(
    ("bridge", "callback", "expected"),
    [
        (True, True, True),
        (False, None, False),
        (None, False, False),
        (True, None, None),
        (None, True, None),
        (None, None, None),
    ],
)
def test_availability_combination_preserves_failure_and_unknown(
    bridge: bool | None,
    callback: bool | None,
    expected: bool | None,
) -> None:
    assert combine_oast_availability(bridge, callback) is expected


def test_lost_ssrf_observer_preserves_previous_zap_gap() -> None:
    current = OastVerification(zap="unverifiable", ssrf="unverifiable", reason="ponte")
    result = mark_ssrf_unobservable(current)
    assert result.zap == "unverifiable"
    assert result.ssrf == "unverifiable"
    assert result.reason is not None


@pytest.mark.parametrize(
    ("zap", "ssrf", "expected"),
    [
        ("verifiable", "verifiable", None),
        ("verifiable", "unverifiable", "SSRF guiado"),
        ("unverifiable", "verifiable", "OAST do ZAP"),
        ("unverifiable", "unverifiable", "SSRF guiado e OAST do ZAP"),
    ],
)
def test_gap_describes_each_unverifiable_capability(
    zap: str,
    ssrf: str,
    expected: str | None,
) -> None:
    verification = OastVerification.model_validate({"zap": zap, "ssrf": ssrf, "reason": "motivo"})
    scan = scan_result([]).model_copy(update={"oast_verification": verification})
    result = oast_gap(scan)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert expected in result
        assert "motivo" in result
