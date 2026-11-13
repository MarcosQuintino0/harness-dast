"""Política, limites, plano, andamento e regras do Replacer: tudo puro, sem I/O."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_plan import (
    EXTRA_OUTCOMES,
    last_sent,
    resolve_targets,
    select_candidates,
)
from harness_dast.domain.scan_policy import (
    DEFAULT_DISABLED_RULES,
    ScanLimits,
    build_limits,
    build_policy,
    delay_ms_for,
    scan_cap_minutes,
)
from harness_dast.domain.scan_result import ScanStatus, interpret_finish
from harness_dast.domain.scan_tokens import (
    build_token_rules,
    jwt_expiry,
    origin_regex,
    refresh_due,
)
from harness_dast.domain.scope import Scope, ScopeGuard
from harness_dast.domain.zap_messages import LearnedRequest, ZapMessage, parse_learned_request
from harness_dast.domain.zap_scope import REPLACER_RULE_PREFIX
from tests.unit.domain.report_helpers import operation

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def limits(**changes: float) -> RunLimits:
    base = {"requests_per_second": 5, "max_duration_minutes": 60, "zap_threads_per_host": 2}
    return RunLimits.model_validate({**base, **changes})


# ----------------------------------------------------------------------------- política


def test_default_policy_is_low_strength_medium_threshold_with_path_injection() -> None:
    policy = build_policy(ScanConfig())

    assert (policy.strength, policy.threshold) == ("LOW", "MEDIUM")
    assert policy.injectable_mask == 35 + 16
    assert set(policy.disabled_rules) == {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}


def test_default_disabled_rules_each_have_a_reason_and_no_duplicates() -> None:
    ids = [rule.plugin_id for rule in DEFAULT_DISABLED_RULES]

    assert len(ids) == len(set(ids))
    assert all(rule.reason and rule.name for rule in DEFAULT_DISABLED_RULES)
    assert {40044, 30001, 30002, 10104} <= set(ids)


def test_profile_rules_only_add_to_the_disabled_set() -> None:
    policy = build_policy(ScanConfig(disable_rules=(90001, 40044)))

    assert 90001 in policy.disabled_rules
    assert len(policy.disabled_rules) == len(DEFAULT_DISABLED_RULES) + 1
    assert list(policy.disabled_rules) == sorted(policy.disabled_rules)


def test_path_injection_off_uses_the_zap_default_mask() -> None:
    assert build_policy(ScanConfig(url_path_injection=False)).injectable_mask == 35


@pytest.mark.parametrize(("rps", "delay"), [(50, 20), (5, 200), (1, 1000), (0.5, 2000), (3, 334)])
def test_request_rate_becomes_a_per_host_delay(rps: float, delay: int) -> None:
    assert delay_ms_for(rps) == delay


@given(st.floats(min_value=0.01, max_value=50, allow_nan=False))
def test_delay_never_allows_more_than_the_requested_rate(rps: float) -> None:
    assert 1000.0 / delay_ms_for(rps) <= rps + 1e-9 or delay_ms_for(rps) == 1


def test_limits_come_from_the_profile_and_are_always_explicit() -> None:
    zap = build_limits(limits(zap_threads_per_host=3), ScanConfig(max_scan_minutes=5))

    assert zap == ScanLimits(
        threads_per_host=3, delay_ms=200, max_scan_minutes=5, max_rule_minutes=2
    )


def test_scan_cap_never_exceeds_profile_or_remaining_time_and_is_at_least_one() -> None:
    zap = ScanLimits(threads_per_host=1, delay_ms=1, max_scan_minutes=10, max_rule_minutes=2)

    assert scan_cap_minutes(zap, 3600) == 10
    assert scan_cap_minutes(zap, 150) == 3
    assert scan_cap_minutes(zap, 5) == 1
    assert scan_cap_minutes(zap, -50) == 1


def test_total_cap_is_never_above_the_total_duration() -> None:
    zap = build_limits(limits(max_duration_minutes=3), ScanConfig(max_scan_minutes=10))

    assert zap.max_scan_minutes == 3
    assert zap.max_rule_minutes <= zap.max_scan_minutes


def test_scan_config_rejects_values_outside_closed_sets() -> None:
    for bad in (
        {"strength": "INSANE"},
        {"threshold": "OFF"},
        {"mutating_methods": ["DELETE"]},
        {"max_scan_minutes": 0},
        {"max_scan_minutes": 61},
        {"token_refresh_seconds": 5},
        {"disable_rules": [-1]},
        {"fail_on": "critical"},
        {"nope": 1},
    ):
        with pytest.raises(ValueError, match="1 validation error"):
            ScanConfig.model_validate(bad)


# ----------------------------------------------------------------------------- andamento


def test_finish_is_completed_truncated_or_stopped() -> None:
    done = ScanStatus(scan_id="0", state="FINISHED", progress=100)
    cut = ScanStatus(scan_id="0", state="FINISHED", progress=45)

    assert interpret_finish(done, stop_requested=False) == "completed"
    assert interpret_finish(cut, stop_requested=False) == "truncated"
    assert interpret_finish(cut, stop_requested=True) == "stopped"
    assert interpret_finish(done, stop_requested=True) == "stopped"


@pytest.mark.parametrize(
    ("state", "finished"),
    [
        ("RUNNING", False),
        ("PAUSED", False),
        ("NOT_STARTED", False),
        ("FINISHED", True),
        ("stopped", True),
    ],
)
def test_state_names_decide_whether_a_scan_finished(state: str, finished: bool) -> None:
    assert ScanStatus(scan_id="0", state=state, progress=0).finished is finished


# ----------------------------------------------------------------------------- plano


def audit_result(
    seq: int,
    operation_id: str,
    method: str,
    path: str,
    status: int,
    *,
    account: str | None = "user_a",
    route: str = "zap",
) -> AuditEntry:
    return AuditEntry(
        seq=seq,
        phase="result",
        timestamp="2026-11-13T00:00:00+00:00",
        method=method,
        scheme="http",
        host="alvo",
        port=80,
        path=path,
        account=account,
        operation_id=operation_id,
        route=route,
        status=status,
        duration_ms=1,
    )


def test_last_sent_keeps_only_zap_route_results_and_the_latest_per_operation() -> None:
    entries = [
        audit_result(1, "a", "GET", "/x/1", 500),
        audit_result(2, "a", "GET", "/x/2", 200),
        audit_result(3, "auth.login", "POST", "/login", 200, route="auth"),
        AuditEntry.model_validate(
            {**audit_result(4, "b", "GET", "/y", 200).model_dump(), "phase": "decision"}
        ),
    ]

    sent = last_sent(entries)

    assert set(sent) == {"a"}
    assert sent["a"].path == "/x/2"
    assert sent["a"].account == "user_a"


def test_candidates_are_grouped_by_account_then_reads_before_writes() -> None:
    ops = [
        operation("w1", "POST", "/w"),
        operation("r1", "GET", "/r1"),
        operation("w2", "POST", "/w2"),
        operation("r2", "GET", "/r2"),
    ]
    accounts = {"w1": "admin", "r1": "user_a", "w2": "user_a", "r2": "admin"}
    sent = {
        op.operation_id: last_sent(
            [
                audit_result(
                    i, op.operation_id, op.method, op.path, 200, account=accounts[op.operation_id]
                )
            ]
        )[op.operation_id]
        for i, op in enumerate(ops, start=1)
    }
    from harness_dast.domain.probe_plan import PlannedOperation

    planned = {
        op.operation_id: PlannedOperation(
            operation_id=op.operation_id, method=op.method, path=op.path, decision="send"
        )
        for op in ops
    }

    candidates, skipped = select_candidates(
        ops, planned, sent, login_path=None, config=ScanConfig()
    )

    assert skipped == ()
    assert [c.result.operation_id for c in candidates] == ["r2", "w1", "r1", "w2"]


def test_extra_outcomes_are_a_closed_list_without_server_or_auth_errors() -> None:
    assert "server_error" not in EXTRA_OUTCOMES
    assert "auth_error" not in EXTRA_OUTCOMES
    assert "success" not in EXTRA_OUTCOMES


def test_unplanned_operations_and_missing_audit_are_skipped_with_reasons() -> None:
    ops = [operation("sumiu", "GET", "/s"), operation("nada", "GET", "/n")]
    from harness_dast.domain.probe_plan import PlannedOperation

    planned = {
        "nada": PlannedOperation(operation_id="nada", method="GET", path="/n", decision="send")
    }

    candidates, skipped = select_candidates(ops, planned, {}, login_path=None, config=ScanConfig())

    assert candidates == ()
    assert {s.operation_id: s.reason for s in skipped} == {
        "sumiu": "not_planned",
        "nada": "not_learned",
    }


def test_resolve_matches_method_path_and_status_and_picks_the_latest_message() -> None:
    from harness_dast.domain.probe_plan import PlannedOperation

    op = operation("a", "POST", "/books")
    sent = {"a": last_sent([audit_result(1, "a", "POST", "/books", 200)])["a"]}
    planned = {
        "a": PlannedOperation(operation_id="a", method="POST", path="/books", decision="send")
    }
    candidates, _ = select_candidates([op], planned, sent, login_path=None, config=ScanConfig())
    learned = [
        LearnedRequest(
            message_id=1, method="POST", url="http://alvo/books", body="old", status=200
        ),
        LearnedRequest(
            message_id=9, method="POST", url="http://alvo/books", body="new", status=200
        ),
        LearnedRequest(
            message_id=12, method="POST", url="http://alvo/books", body="err", status=500
        ),
        LearnedRequest(message_id=13, method="GET", url="http://alvo/books", body=None, status=200),
    ]
    guard = ScopeGuard(
        Scope.model_validate(
            {
                "allow": [
                    {
                        "host": "alvo",
                        "scheme": "http",
                        "paths": ["/**"],
                        "methods": ["GET", "POST"],
                        "allow_local": True,
                    }
                ]
            }
        )
    )

    plan = resolve_targets(candidates, sent, learned, guard)

    assert [(t.message_id, t.body) for t in plan.targets] == [(9, "new")]
    assert [(r.operation_id, r.message_id) for r in plan.learned] == [("a", 9)]
    assert "http://alvo/books" not in repr(plan.targets[0])


# ----------------------------------------------------------------------------- mensagens


def message(header: str, status: str = "HTTP/1.1 200 OK", body: str = "") -> ZapMessage:
    return ZapMessage(id=3, request_header=header, request_body=body, response_header=status)


def test_learned_request_is_read_from_the_absolute_request_line() -> None:
    learned = parse_learned_request(
        message("POST http://vampi:5000/books/v1 HTTP/1.1\r\nHost: vampi:5000\r\n", body='{"a":1}'),
        "http",
    )

    assert learned is not None
    assert (learned.method, learned.url, learned.body, learned.status) == (
        "POST",
        "http://vampi:5000/books/v1",
        '{"a":1}',
        200,
    )


def test_origin_form_request_line_uses_the_host_header_and_scheme() -> None:
    learned = parse_learned_request(
        message("GET /me?x=1 HTTP/1.1\r\nHost: api.exemplo.com\r\n"), "https"
    )

    assert learned is not None
    assert learned.url == "https://api.exemplo.com/me?x=1"
    assert learned.body is None


@pytest.mark.parametrize(
    "header",
    [
        "",
        "lixo sem forma",
        "GET relativo HTTP/1.1",
        "GET /x HTTP/1.1\r\n",
        "get http://x/ HTTP/1.1",
    ],
)
def test_unreadable_request_lines_give_none(header: str) -> None:
    assert parse_learned_request(message(header), "http") is None


def test_missing_status_line_leaves_status_none() -> None:
    learned = parse_learned_request(message("GET http://x/ HTTP/1.1", status="???"), "http")

    assert learned is not None
    assert learned.status is None


# ----------------------------------------------------------------------------- Replacer


def test_token_rules_use_the_prefix_and_only_the_target_origin() -> None:
    url = origin_regex("https://api.hml.exemplo.com.br")

    rules = build_token_rules(
        label="user_a",
        generation=3,
        auth_headers=(("Authorization", "Bearer tok"),),
        csrf=None,
        csrf_value=None,
        url_regex=url,
    )

    assert [r.description for r in rules] == [f"{REPLACER_RULE_PREFIX}auth-user_a-3-1"]
    assert rules[0].url == url
    assert url.startswith("^https://")
    assert "tok" not in repr(rules[0])


def test_origin_regex_handles_default_and_custom_ports() -> None:
    assert origin_regex("https://h.com").endswith("(?::443)?/.*")
    assert origin_regex("http://h.com").endswith("(?::80)?/.*")
    assert origin_regex("http://127.0.0.1:8080").endswith(":8080/.*")


def test_csrf_rules_replace_the_header_and_only_the_cookie_value() -> None:
    csrf = CsrfConfig(fetch_path="/api/csrf", cookie_name="XSRF-TOKEN", header_name="X-XSRF-TOKEN")

    rules = build_token_rules(
        label="user_a",
        generation=1,
        auth_headers=(("Authorization", "Bearer t"),),
        csrf=csrf,
        csrf_value="a$b\\c",
        url_regex="^x",
    )

    header, cookie = rules[1], rules[2]
    assert header.match_type == "REQ_HEADER"
    assert header.replacement == "a$b\\c"
    assert cookie.match_type == "REQ_HEADER_STR"
    assert cookie.regex is True
    assert cookie.replacement == "XSRF-TOKEN=a\\$b\\\\c"
    assert "XSRF\\-TOKEN" in cookie.match_string


def test_jwt_expiry_reads_exp_and_rejects_everything_else() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjE4MDAwMDAwMDB9.assinatura"  # noqa: S105 - JWT de teste

    assert jwt_expiry(token) == datetime.fromtimestamp(1_800_000_000, tz=UTC)
    assert jwt_expiry(f"Bearer {token}") == datetime.fromtimestamp(1_800_000_000, tz=UTC)
    for bad in (
        "",
        "a.b",
        "a.b.c",
        "eyJ.e30.x",
        "x.!!!.y",
        "a.eyJleHAiOiJ0ZXh0byJ9.c",
        "a.eyJleHAiOnRydWV9.c",
    ):
        assert jwt_expiry(bad) is None
    assert jwt_expiry("a.eyJleHAiOjFlMzAwfQ.c") is None


def test_refresh_is_due_by_age_or_by_proximity_to_expiry() -> None:
    def due(seconds: int) -> bool:
        return refresh_due(
            issued_at=NOW,
            now=NOW + timedelta(seconds=seconds),
            interval_seconds=120,
            expires_at=None,
        )

    assert due(119) is False
    assert due(120) is True
    soon = NOW + timedelta(seconds=100)
    assert (
        refresh_due(
            now=NOW + timedelta(seconds=80), issued_at=NOW, interval_seconds=120, expires_at=soon
        )
        is True
    )
    far = NOW + timedelta(hours=1)
    assert (
        refresh_due(
            now=NOW + timedelta(seconds=80), issued_at=NOW, interval_seconds=120, expires_at=far
        )
        is False
    )
