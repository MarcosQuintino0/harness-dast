"""Classificação de respostas do `probe` e decisão de nova tentativa."""

import pytest

from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.outcome import (
    SENT_OUTCOMES,
    Outcome,
    classify_response,
    looks_like_csrf_rejection,
    parse_json_body,
)
from harness_dast.domain.probe_config import JsonFieldRule
from harness_dast.domain.retry import RetryAction, RetryState, next_action

CSRF = CsrfConfig(fetch_path="/api/csrf")
FAIL_RULE = JsonFieldRule(field="status", value="fail")


def response(status: int, body: bytes = b"", truncated: bool = False) -> HttpResponse:
    return HttpResponse(status=status, body=body, body_truncated=truncated)


def classify(
    status: int, body: bytes = b"", method: str = "GET", rule: JsonFieldRule | None = None
) -> Outcome:
    return classify_response(response(status, body), method=method, success_rule=rule, csrf=CSRF)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "success"),
        (201, "success"),
        (204, "success"),
        (301, "redirect"),
        (302, "redirect"),
        (400, "validation_error"),
        (422, "validation_error"),
        (401, "auth_error"),
        (403, "auth_error"),
        (404, "not_found"),
        (410, "not_found"),
        (409, "conflict"),
        (429, "rate_limited"),
        (405, "client_error"),
        (415, "client_error"),
        (500, "server_error"),
        (503, "server_error"),
    ],
)
def test_status_maps_to_the_expected_class(status: int, expected: str) -> None:
    assert classify(status, b'{"message":"detalhe"}') == expected


def test_a_2xx_with_a_failure_body_is_a_logical_failure_when_the_profile_says_so() -> None:
    assert classify(200, b'{"status":"fail","message":"x"}', rule=FAIL_RULE) == "logical_failure"


@pytest.mark.parametrize(
    "body",
    [b'{"status":"success"}', b"{}", b"", b"nao e json", b"[1,2]", b'{"status":null}'],
)
def test_a_2xx_without_the_failure_marker_is_a_success_even_with_the_rule(body: bytes) -> None:
    assert classify(200, body, rule=FAIL_RULE) == "success"


def test_without_a_rule_a_failure_body_inside_a_2xx_is_still_a_success() -> None:
    assert classify(200, b'{"status":"fail"}') == "success"


def test_the_rule_compares_types_so_one_is_not_true() -> None:
    rule = JsonFieldRule(field="ok", value=True)

    assert rule.is_failure({"ok": True}) is True
    assert rule.is_failure({"ok": 1}) is False
    assert JsonFieldRule(field="a.b", value=0).is_failure({"a": {"b": 0}}) is True
    assert JsonFieldRule(field="a.b", value=0).is_failure({"a": 3}) is False


def test_error_statuses_ignore_the_success_rule() -> None:
    assert classify(400, b'{"status":"ok"}', rule=FAIL_RULE) == "validation_error"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"message":"Invalid CSRF Token found"}', True),
        (b"<h1>XSRF token mismatch</h1>", True),
        (b"", True),
        (b'{"timestamp":"t","status":403,"error":"Forbidden","path":"/x"}', True),
        (b'{"message":"sem permissao"}', False),
        (b'{"error":"Forbidden","message":""}', False),
        (b"acesso negado", False),
    ],
)
def test_a_403_looks_like_csrf_only_in_the_expected_shapes(body: bytes, expected: bool) -> None:
    assert looks_like_csrf_rejection(response(403, body), "POST", CSRF) is expected


def test_a_403_on_a_method_without_csrf_or_without_config_is_never_csrf() -> None:
    forbidden = response(403, b"csrf")
    assert looks_like_csrf_rejection(forbidden, "GET", CSRF) is False
    assert looks_like_csrf_rejection(forbidden, "POST", None) is False
    assert looks_like_csrf_rejection(response(401, b"csrf"), "POST", CSRF) is False


def test_csrf_403_is_classified_as_csrf_error_and_plain_403_as_auth_error() -> None:
    assert classify(403, b'{"message":"CSRF"}', method="POST") == "csrf_error"
    assert classify(403, b'{"message":"CSRF"}', method="GET") == "auth_error"
    assert classify(403, b'{"message":"nao pode"}', method="POST") == "auth_error"


def test_parse_json_body_gives_none_for_empty_truncated_or_invalid_bodies() -> None:
    assert parse_json_body(response(200, b'{"a":1}')) == {"a": 1}
    assert parse_json_body(response(200, b"")) is None
    assert parse_json_body(response(200, b'{"a":1}', truncated=True)) is None
    assert parse_json_body(response(200, b"{oops")) is None
    assert parse_json_body(response(200, b"[" * 100_000)) is None


def test_sent_outcomes_exclude_every_skipped_class() -> None:
    assert "success" in SENT_OUTCOMES
    assert "timeout" in SENT_OUTCOMES
    assert not {o for o in SENT_OUTCOMES if o.startswith("skipped")}
    assert "build_error" not in SENT_OUTCOMES
    assert "dry_run" not in SENT_OUTCOMES


def next_for(
    status: int,
    body: bytes = b"",
    method: str = "POST",
    can_reauth: bool = True,
    state: RetryState | None = None,
) -> RetryAction:
    return next_action(
        response(status, body),
        method,
        csrf=CSRF,
        can_reauth=can_reauth,
        state=state or RetryState(),
    )


def test_a_401_reauthenticates_once() -> None:
    assert next_for(401) == "reauth"
    assert next_for(401, state=RetryState(reauths=1)) == "done"
    assert next_for(401, can_reauth=False) == "done"


def test_a_csrf_looking_403_refreshes_once() -> None:
    assert next_for(403, b'{"message":"csrf"}') == "refresh_csrf"
    assert next_for(403, b'{"message":"csrf"}', state=RetryState(csrf_refreshes=1)) == "done"
    assert next_for(403, b'{"message":"csrf"}', method="GET") == "done"


def test_a_429_waits_three_times_at_most() -> None:
    assert next_for(429) == "wait"
    assert next_for(429, state=RetryState(waits=2)) == "wait"
    assert next_for(429, state=RetryState(waits=3)) == "done"


@pytest.mark.parametrize("status", [200, 400, 404, 500, 302])
def test_other_statuses_end_the_operation(status: int) -> None:
    assert next_for(status) == "done"


def test_retry_state_counts_each_action_without_mutating_the_original() -> None:
    state = RetryState()

    after = state.after("wait").after("wait").after("reauth").after("refresh_csrf")

    assert (after.waits, after.reauths, after.csrf_refreshes) == (2, 1, 1)
    assert state == RetryState()
    assert state.after("done") == state
