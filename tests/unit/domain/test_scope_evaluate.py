"""`ScopeGuard.evaluate`: a decisão como dado, coerente com `ensure_allowed`."""

import pytest

from harness_dast.domain.errors import (
    ExitCode,
    HarnessError,
    ScopeViolation,
    TargetError,
    TargetTimeout,
    TargetUnreachable,
)
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule

HOST = "api.permitido.com"


def guard() -> ScopeGuard:
    rule = ScopeRule(host=HOST, paths=("/api/**",), methods=("GET",))
    return ScopeGuard(Scope(allow=(rule,), deny_paths=("/api/admin/**",)))


@pytest.mark.parametrize(
    ("method", "url", "verdict"),
    [
        ("GET", f"https://{HOST}/api/x", "allowed"),
        ("GET", f"https://{HOST}/api/admin/x", "denied_path"),
        ("GET", f"https://{HOST}/API/ADMIN/x", "denied_path"),
        ("GET", f"https://{HOST}/fora", "outside_scope"),
        ("POST", f"https://{HOST}/api/x", "outside_scope"),
        ("GET", "https://outro.example.org/api/x", "outside_scope"),
        ("GET", f"https://{HOST}/api/../x", "outside_scope"),
        ("GET", "not a url", "outside_scope"),
    ],
)
def test_verdict_matches_what_ensure_allowed_would_do(method: str, url: str, verdict: str) -> None:
    request = OutboundRequest(method=method, url=url)
    decision = guard().evaluate(request)

    assert decision.verdict == verdict
    if verdict == "allowed":
        guard().ensure_allowed(request)
        assert decision.reason is None
    else:
        with pytest.raises(ScopeViolation):
            guard().ensure_allowed(request)
        assert decision.reason


def test_the_reason_never_repeats_the_path() -> None:
    decision = guard().evaluate(
        OutboundRequest(method="GET", url=f"https://{HOST}/api/admin/tok-123")
    )

    assert "tok-123" not in (decision.reason or "")


def test_transport_errors_are_target_errors_with_distinct_codes() -> None:
    timeout = TargetTimeout("lento")
    unreachable = TargetUnreachable("caiu")

    for error in (timeout, unreachable):
        assert isinstance(error, TargetError)
        assert isinstance(error, HarnessError)
        assert error.exit_code == ExitCode.TARGET
    assert timeout.code == "TARGET_TIMEOUT"
    assert unreachable.code == "TARGET_UNREACHABLE"
