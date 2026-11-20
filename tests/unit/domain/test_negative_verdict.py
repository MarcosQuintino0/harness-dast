"""Veredito da reação e severidade proposta (ADR 0051)."""

import pytest

from harness_dast.domain.negative_values import CLASS_ORDER, CaseClass
from harness_dast.domain.negative_verdict import STOP_REASONS, judge, proposed_severity, reason_text


@pytest.mark.parametrize(
    ("status", "verdict", "reason"),
    [
        (200, "accepted", None),
        (201, "accepted", None),
        (204, "accepted", None),
        (301, "inconclusive", "redirect"),
        (302, "inconclusive", "redirect"),
        (400, "rejected", None),
        (401, "inconclusive", "unauthorized"),
        (403, "inconclusive", "unauthorized"),
        (404, "inconclusive", "not_found"),
        (405, "inconclusive", "method_not_allowed"),
        (409, "inconclusive", "conflict"),
        (410, "inconclusive", "not_found"),
        (413, "rejected", None),
        (415, "rejected", None),
        (422, "rejected", None),
        (429, "inconclusive", "rate_limited"),
        (500, "server_error", None),
        (502, "server_error", None),
        (503, "server_error", None),
        (None, "inconclusive", "no_response"),
        (99, "inconclusive", "unexpected_status"),
        (600, "inconclusive", "unexpected_status"),
    ],
)
def test_the_status_table_for_a_get(status: int | None, verdict: str, reason: str | None) -> None:
    reaction = judge(status, "GET")

    assert reaction.verdict == verdict
    assert reaction.reason == reason


def test_a_409_on_a_post_is_a_create_conflict() -> None:
    assert judge(409, "POST").reason == "create_conflict"
    assert judge(409, "put").reason == "conflict"


def test_only_a_lost_account_or_a_gone_resource_end_the_operation() -> None:
    assert {"unauthorized", "not_found"} == STOP_REASONS


def test_every_reason_has_a_sentence() -> None:
    for status in (401, 404, 405, 409, 429, 301, None, 99):
        reason = judge(status, "GET").reason
        assert reason is not None
        assert reason_text(reason) != reason
    assert reason_text("create_conflict") != "create_conflict"


@pytest.mark.parametrize("verdict", ["accepted", "server_error"])
@pytest.mark.parametrize("case_class", CLASS_ORDER)
def test_a_get_is_always_low(case_class: CaseClass, verdict: str) -> None:
    assert proposed_severity("GET", case_class, verdict) == "low"  # type: ignore[arg-type]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_a_write_is_medium_except_accepting_a_wrong_type(method: str) -> None:
    for case_class in CLASS_ORDER:
        expected = "low" if case_class == "wrong_type" else "medium"
        assert proposed_severity(method, case_class, "accepted") == expected
        assert proposed_severity(method, case_class, "server_error") == "medium"
