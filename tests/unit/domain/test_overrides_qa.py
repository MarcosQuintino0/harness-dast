"""Testes independentes (QA): sobrescritas só podem estreitar escopo e limites."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError, HarnessError
from harness_dast.domain.overrides import (
    LimitsOverride,
    ScopeOverride,
    narrow_limits,
    narrow_scope,
)
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule


def base_scope() -> Scope:
    return Scope(
        allow=(
            ScopeRule(host="a.example.com", paths=("/api/**",), methods=("GET", "POST")),
            ScopeRule(host="b.example.com", paths=("/v1/*", "/health"), methods=("GET",)),
        ),
        deny_paths=("/api/admin/**",),
    )


def _permits(scope: Scope, method: str, url: str) -> bool:
    from harness_dast.domain.errors import ScopeViolation

    try:
        ScopeGuard(scope).ensure_allowed(OutboundRequest(method=method, url=url))
    except ScopeViolation:
        return False
    return True


PROBES = [
    (m, f"https://{h}{p}")
    for m in ("GET", "POST", "PUT", "DELETE")
    for h in ("a.example.com", "b.example.com", "c.example.com")
    for p in (
        "/api/x",
        "/api/x/y",
        "/api",
        "/api/admin/x",
        "/v1/z",
        "/v1/z/w",
        "/health",
        "/",
        "/other",
    )
]


def _assert_subset(narrow: Scope, wide: Scope) -> None:
    for method, url in PROBES:
        if _permits(narrow, method, url):
            assert _permits(wide, method, url), (method, url)


@pytest.mark.parametrize(
    "override",
    [
        ScopeOverride(hosts=("a.example.com",)),
        ScopeOverride(hosts=("A.EXAMPLE.COM.",)),
        ScopeOverride(methods=("GET",)),
        ScopeOverride(paths=("/api/x/**",)),
        ScopeOverride(paths=("/api/*",)),
        ScopeOverride(paths=("/v1/a",)),
        ScopeOverride(hosts=("b.example.com",), methods=("GET",), paths=("/health",)),
        ScopeOverride(deny_paths=("/api/x/**",)),
        ScopeOverride(),
    ],
)
def test_narrow_scope_never_permits_more_when_override_is_valid(override: ScopeOverride) -> None:
    wide = base_scope()

    narrowed = narrow_scope(wide, override)

    _assert_subset(narrowed, wide)


@pytest.mark.parametrize(
    "override",
    [
        ScopeOverride(hosts=("evil.com",)),
        ScopeOverride(hosts=("a.example.com", "evil.com")),
        ScopeOverride(hosts=("sub.a.example.com",)),
        ScopeOverride(methods=("DELETE",)),
        ScopeOverride(methods=("GET", "PUT")),
        ScopeOverride(paths=("/**",)),
        ScopeOverride(paths=("/api2/**",)),
        ScopeOverride(paths=("/admin",)),
        ScopeOverride(paths=("/api/**", "/other")),
        ScopeOverride(paths=("/v1/**",)),
        ScopeOverride(hosts=()),
        ScopeOverride(methods=()),
        ScopeOverride(paths=()),
    ],
)
def test_narrow_scope_raises_config_error_when_override_would_widen_or_empty(
    override: ScopeOverride,
) -> None:
    with pytest.raises(ConfigError):
        narrow_scope(base_scope(), override)


def test_narrow_scope_keeps_profile_denials_when_override_adds_more() -> None:
    narrowed = narrow_scope(base_scope(), ScopeOverride(deny_paths=("/api/x",)))

    assert not _permits(narrowed, "GET", "https://a.example.com/api/admin/x")
    assert not _permits(narrowed, "GET", "https://a.example.com/api/x")
    assert _permits(narrowed, "GET", "https://a.example.com/api/y")


def test_narrow_scope_does_not_mutate_arguments() -> None:
    scope = base_scope()
    override = ScopeOverride(hosts=("a.example.com",), methods=("GET",))
    before = (scope.model_dump(), override.model_dump())

    narrow_scope(scope, override)

    assert (scope.model_dump(), override.model_dump()) == before


def test_narrow_scope_does_not_resurrect_a_rule_when_host_is_repeated_in_override() -> None:
    narrowed = narrow_scope(base_scope(), ScopeOverride(hosts=("a.example.com", "a.example.com")))

    assert len(narrowed.allow) == 1


def test_narrow_scope_keeps_each_host_methods_when_override_methods_are_common() -> None:
    narrowed = narrow_scope(base_scope(), ScopeOverride(methods=("GET",)))

    assert not _permits(narrowed, "POST", "https://a.example.com/api/x")
    assert _permits(narrowed, "GET", "https://a.example.com/api/x")
    assert not _permits(narrowed, "DELETE", "https://b.example.com/v1/z")


def test_narrow_scope_does_not_apply_path_of_one_host_to_another_when_paths_overlap() -> None:
    narrowed = narrow_scope(base_scope(), ScopeOverride(paths=("/health",)))

    assert not _permits(narrowed, "GET", "https://a.example.com/health")
    assert _permits(narrowed, "GET", "https://b.example.com/health")


_toks = st.lists(st.sampled_from(["api", "v1", "x", "*", "**"]), min_size=0, max_size=4)


@settings(max_examples=200, deadline=None)
@given(paths=st.lists(_toks, min_size=1, max_size=3))
def test_narrow_scope_is_subset_when_paths_are_random(paths: list[list[str]]) -> None:
    override = ScopeOverride(paths=tuple("/" + "/".join(p) for p in paths))
    wide = base_scope()
    try:
        narrowed = narrow_scope(wide, override)
    except HarnessError:
        return
    _assert_subset(narrowed, wide)


# ---------------------------------------------------------------- limits
LIMITS = RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2)


def test_narrow_limits_returns_equal_limits_when_override_is_empty() -> None:
    assert narrow_limits(LIMITS, LimitsOverride()) == LIMITS


def test_narrow_limits_takes_the_smaller_when_override_is_lower() -> None:
    result = narrow_limits(
        LIMITS,
        LimitsOverride(requests_per_second=1.5, max_duration_minutes=10, zap_threads_per_host=1),
    )

    assert (
        result.requests_per_second,
        result.max_duration_minutes,
        result.zap_threads_per_host,
    ) == (
        1.5,
        10,
        1,
    )


def test_narrow_limits_accepts_override_equal_to_profile() -> None:
    assert (
        narrow_limits(LIMITS, LimitsOverride(requests_per_second=5, max_duration_minutes=60))
        == LIMITS
    )


@pytest.mark.parametrize(
    "override",
    [
        LimitsOverride(requests_per_second=5.0000001),
        LimitsOverride(max_duration_minutes=61),
        LimitsOverride(zap_threads_per_host=3),
        LimitsOverride(requests_per_second=50, max_duration_minutes=1),
        LimitsOverride(requests_per_second=1, zap_threads_per_host=8),
    ],
)
def test_narrow_limits_raises_when_any_field_widens(override: LimitsOverride) -> None:
    with pytest.raises(ConfigError):
        narrow_limits(LIMITS, override)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"requests_per_second": 0},
        {"requests_per_second": -1},
        {"requests_per_second": float("nan")},
        {"requests_per_second": float("inf")},
        {"requests_per_second": True},
        {"requests_per_second": "2"},
        {"requests_per_second": 50.01},
        {"max_duration_minutes": 0},
        {"max_duration_minutes": -5},
        {"max_duration_minutes": True},
        {"max_duration_minutes": 1.5},
        {"max_duration_minutes": "10"},
        {"max_duration_minutes": 481},
        {"zap_threads_per_host": 0},
        {"zap_threads_per_host": 9},
        {"zap_threads_per_host": False},
    ],
)
def test_limits_override_rejects_when_value_is_out_of_range_or_wrong_type(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        LimitsOverride.model_validate(kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hosts": ("*.example.com",)},
        {"methods": ("get",)},
        {"methods": ("TRACE",)},
        {"paths": ("api",)},
        {"paths": ("/api/../x",)},
        {"deny_paths": ("/a/us*",)},
        {"unknown": 1},
    ],
)
def test_scope_override_rejects_when_input_is_invalid(kwargs: dict[str, object]) -> None:
    try:
        override = ScopeOverride.model_validate(kwargs)
    except ValidationError:
        return
    # Se o modelo aceitar, a aplicação não pode ampliar nem aceitar curinga de host.
    with pytest.raises(HarnessError):
        narrow_scope(base_scope(), override)


def test_narrow_limits_does_not_mutate_arguments() -> None:
    override = LimitsOverride(requests_per_second=1)
    before = (LIMITS.model_dump(), override.model_dump())

    narrow_limits(LIMITS, override)

    assert (LIMITS.model_dump(), override.model_dump()) == before


def test_narrow_limits_result_respects_hard_maxima_when_profile_is_at_maximum() -> None:
    top = RunLimits(requests_per_second=50, max_duration_minutes=480, zap_threads_per_host=8)

    assert narrow_limits(top, LimitsOverride(requests_per_second=50)) == top
    with pytest.raises(ValidationError):
        LimitsOverride(requests_per_second=51)
