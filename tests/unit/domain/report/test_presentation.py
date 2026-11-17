"""Contratos de calibração, filtro e apresentação segura."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.report.presentation import (
    CalibrationMeasurement,
    Presentation,
    PresentedFinding,
    calibration_text,
    parse_calibration,
)
from harness_dast.domain.report.presentation_render import render_presentation_html
from harness_dast.domain.verification import VerificationEntry


@pytest.mark.parametrize(("sample", "expected"), [(9, False), (10, True)])
def test_percentage_requires_minimum_sample(sample: int, expected: bool) -> None:
    item = CalibrationMeasurement(
        finding_type="XSS", criterion="acertos", correct=4, sample=sample, provenance="lab"
    )
    result = calibration_text(item)
    assert (result is not None) is expected
    if result:
        assert "4 de 10" in result
        assert "40.0%" in result
        assert "XSS" in result


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"schema_version": True},
        {"schema_version": 1, "status": "measured", "provenance": "lab", "measurements": []},
    ],
)
def test_invalid_calibration_is_rejected(data: object) -> None:
    with pytest.raises(ConfigError):
        parse_calibration(data)


def test_blocked_calibration_contains_no_measurement() -> None:
    result = parse_calibration(
        {
            "schema_version": 1,
            "status": "blocked",
            "provenance": "sem aprovação",
            "measurements": [],
        }
    )
    assert result.measurements == ()


@pytest.mark.parametrize(
    ("severity", "level", "expected"),
    [
        ("high", "likely", True),
        ("high", "reproduced", False),
        ("low", "inconclusive", True),
        ("low", "not_verifiable", False),
    ],
)
def test_person_filter_selects_only_expected_findings(
    severity: str, level: str, expected: bool
) -> None:
    entry = VerificationEntry.model_validate(
        {"fingerprint": "a" * 64, "level": level, "reason": "teste"}
    )
    item = PresentedFinding(
        finding_id="F-abc", title="teste", severity=severity, origin="zap", verification=entry
    )
    assert item.needs_person is expected
    assert f"Precisa de uma pessoa ({int(expected)})" in render_presentation_html(
        Presentation(findings=(item,))
    )
