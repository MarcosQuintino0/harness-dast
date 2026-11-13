"""Alerta bruto do ZAP: leitura tolerante de campos e severidade/confiança propostas."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding_taxonomy import OWASP_API_2023, owasp_api_category
from harness_dast.domain.fix_hints import DEFAULT_HINT, fix_hint
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.zap_alert import (
    RawAlert,
    evidence_candidates,
    int_or_none,
    parse_confidence,
    parse_severity,
)
from tests.fakes.zap_alerts import zap_alert


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        ("High", "high"),
        ("high", "high"),
        ("Medium", "medium"),
        ("Low", "low"),
        ("Informational", "informational"),
        ("Info", "informational"),
        ("High (Medium)", "high"),
        ("", "unknown"),
        ("Critical", "unknown"),
        ("🔥", "unknown"),
    ],
)
def test_severity_is_read_as_proposed_and_unknown_is_never_guessed(
    risk: str, expected: str
) -> None:
    assert parse_severity(risk) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("High", "high"),
        ("Medium", "medium"),
        ("Low", "low"),
        ("False Positive", "false_positive"),
        ("User Confirmed", "confirmed"),
        ("", "unknown"),
        ("???", "unknown"),
    ],
)
def test_confidence_is_read_as_proposed(value: str, expected: str) -> None:
    assert parse_confidence(value) == expected


def test_alert_reads_the_zap_camel_case_names_from_the_spike() -> None:
    alert = RawAlert.model_validate(zap_alert("7", alertRef="40018-2"))

    assert (alert.id, alert.plugin_id, alert.alert_ref) == ("7", "40018", "40018-2")
    assert (alert.cwe_id, alert.wasc_id) == ("89", "19")
    assert (alert.input_vector, alert.message_id, alert.source_message_id) == (
        "urlpath",
        "1604",
        "4",
    )


def test_alert_accepts_numbers_and_ignores_unknown_fields_but_rejects_structures() -> None:
    alert = RawAlert.model_validate({"id": 5, "pluginId": 40018, "campo_novo": [1]})

    assert (alert.id, alert.plugin_id) == ("5", "40018")
    with pytest.raises(ValidationError):
        RawAlert.model_validate({"id": ["x"]})


@pytest.mark.parametrize(
    ("text", "expected"),
    [("89", 89), (" 79 ", 79), ("-1", None), ("0", None), ("", None), ("x", None), ("١٢", None)],
)
def test_ids_that_are_not_positive_ascii_integers_are_none(text: str, expected: int | None) -> None:
    assert int_or_none(text) == expected


def test_evidence_candidates_are_distinct_ranked_and_capped() -> None:
    alerts = [
        RawAlert.model_validate(zap_alert("1", risk="Low", messageId="10")),
        RawAlert.model_validate(zap_alert("2", risk="High", confidence="Low", messageId="20")),
        RawAlert.model_validate(zap_alert("3", risk="High", confidence="High", messageId="30")),
        RawAlert.model_validate(zap_alert("4", risk="High", confidence="High", messageId="30")),
        RawAlert.model_validate(zap_alert("5", messageId="")),
    ]

    assert evidence_candidates(alerts, 10) == (30, 20, 10)
    assert evidence_candidates(alerts, 2) == (30, 20)


def test_owasp_mapping_is_small_and_has_no_cwe_that_belongs_to_two_categories() -> None:
    assert owasp_api_category(918) == "API7:2023 Server Side Request Forgery"
    assert owasp_api_category(89) is None
    assert owasp_api_category(None) is None
    assert 285 not in OWASP_API_2023
    assert 319 not in OWASP_API_2023
    assert len(OWASP_API_2023) <= 20


def test_fix_hints_are_generic_text_with_a_default() -> None:
    assert "parametrizadas" in fix_hint(89)
    assert fix_hint(None) == DEFAULT_HINT
    assert fix_hint(99999) == DEFAULT_HINT


def test_run_ids_are_validated_without_echoing_the_input() -> None:
    good = "2026-11-13T05-15-32Z-vampi-ab12"

    assert require_run_id(good) == good
    with pytest.raises(ConfigError) as info:
        require_run_id("../../segredo")
    assert "segredo" not in info.value.message
