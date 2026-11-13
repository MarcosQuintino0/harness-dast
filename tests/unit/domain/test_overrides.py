import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.overrides import (
    LimitsOverride,
    ScopeOverride,
    narrow_limits,
    narrow_scope,
)
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scope import Scope, ScopeRule


def base_scope() -> Scope:
    return Scope(
        allow=(
            ScopeRule(host="a.permitido.com", paths=("/api/**",), methods=("GET", "POST", "PUT")),
            ScopeRule(host="b.permitido.com", paths=("/v2/*", "/health"), methods=("GET",)),
        ),
        deny_paths=("/api/admin/**",),
    )


def base_limits() -> RunLimits:
    return RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2)


# ----------------------------------------------------------------------- escopo


def test_narrow_scope_returns_equal_scope_when_override_is_empty() -> None:
    scope = base_scope()

    assert narrow_scope(scope, ScopeOverride()) == scope


def test_narrow_scope_keeps_only_requested_hosts_when_hosts_are_a_subset() -> None:
    result = narrow_scope(base_scope(), ScopeOverride(hosts=("A.Permitido.com",)))

    assert [rule.host for rule in result.allow] == ["a.permitido.com"]


def test_narrow_scope_intersects_methods_when_methods_are_a_subset() -> None:
    result = narrow_scope(base_scope(), ScopeOverride(methods=("GET",)))

    assert [(r.host, r.methods) for r in result.allow] == [
        ("a.permitido.com", ("GET",)),
        ("b.permitido.com", ("GET",)),
    ]


def test_narrow_scope_drops_rules_without_requested_method_when_method_is_in_one_rule_only() -> (
    None
):
    result = narrow_scope(base_scope(), ScopeOverride(methods=("PUT",)))

    assert [r.host for r in result.allow] == ["a.permitido.com"]


def test_narrow_scope_keeps_covered_paths_when_requested_paths_are_narrower() -> None:
    result = narrow_scope(base_scope(), ScopeOverride(paths=("/api/users/*", "/health")))

    assert [(r.host, r.paths) for r in result.allow] == [
        ("a.permitido.com", ("/api/users/*",)),
        ("b.permitido.com", ("/health",)),
    ]


def test_narrow_scope_adds_deny_paths_without_removing_existing_ones() -> None:
    result = narrow_scope(base_scope(), ScopeOverride(deny_paths=("/api/pagamentos/**",)))

    assert result.deny_paths == ("/api/admin/**", "/api/pagamentos/**")


def test_narrow_scope_does_not_duplicate_deny_paths_when_override_repeats_one() -> None:
    result = narrow_scope(base_scope(), ScopeOverride(deny_paths=("/api/admin/**",)))

    assert result.deny_paths == ("/api/admin/**",)


def test_narrow_scope_does_not_mutate_arguments_when_called() -> None:
    scope = base_scope()
    override = ScopeOverride(hosts=("a.permitido.com",), methods=("GET",))

    narrow_scope(scope, override)

    assert scope == base_scope()


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        pytest.param(ScopeOverride(hosts=("c.outro.com",)), "host", id="host_not_in_profile"),
        pytest.param(
            ScopeOverride(hosts=("a.permitido.com", "c.outro.com")), "host", id="host_mixed"
        ),
        pytest.param(ScopeOverride(methods=("DELETE",)), "método", id="method_not_in_profile"),
        pytest.param(ScopeOverride(paths=("/admin/**",)), "caminho", id="path_outside_profile"),
        pytest.param(ScopeOverride(paths=("/**",)), "caminho", id="path_wider_than_profile"),
        pytest.param(ScopeOverride(paths=("/api/**", "/v2/**")), "caminho", id="path_wider_in_b"),
        pytest.param(ScopeOverride(paths=("/v2/**",)), "caminho", id="double_star_wider_than_star"),
    ],
)
def test_narrow_scope_raises_config_error_when_override_would_widen(
    override: ScopeOverride, fragment: str
) -> None:
    with pytest.raises(ConfigError, match=fragment) as caught:
        narrow_scope(base_scope(), override)

    assert "amplia" in caught.value.message
    assert caught.value.hint


def test_narrow_scope_raises_config_error_when_override_leaves_no_rules() -> None:
    with pytest.raises(ConfigError, match="nenhuma regra"):
        narrow_scope(base_scope(), ScopeOverride(hosts=()))


def test_narrow_scope_rejects_method_when_host_filter_removed_the_only_rule_that_had_it() -> None:
    override = ScopeOverride(hosts=("b.permitido.com",), methods=("POST",))

    with pytest.raises(ConfigError, match="método"):
        narrow_scope(base_scope(), override)


def test_scope_override_rejects_invalid_values_when_built_from_bad_input() -> None:
    with pytest.raises(ValidationError):
        ScopeOverride(methods=("get",))
    with pytest.raises(ValidationError):
        ScopeOverride(paths=("/a/../b",))
    with pytest.raises(ValidationError):
        ScopeOverride(deny_paths=("sem-barra",))
    with pytest.raises(ValidationError):
        ScopeOverride.model_validate({"hots": ["a"]})


# ---------------------------------------------------------------------- limites


def test_narrow_limits_returns_same_limits_when_override_is_empty() -> None:
    assert narrow_limits(base_limits(), LimitsOverride()) == base_limits()


def test_narrow_limits_lowers_each_field_when_values_are_smaller() -> None:
    result = narrow_limits(
        base_limits(),
        LimitsOverride(requests_per_second=1, max_duration_minutes=10, zap_threads_per_host=1),
    )

    assert (
        result.requests_per_second,
        result.max_duration_minutes,
        result.zap_threads_per_host,
    ) == (
        1,
        10,
        1,
    )


def test_narrow_limits_accepts_value_equal_to_profile() -> None:
    result = narrow_limits(base_limits(), LimitsOverride(max_duration_minutes=60))

    assert result == base_limits()


@pytest.mark.parametrize(
    ("override", "field"),
    [
        pytest.param(LimitsOverride(requests_per_second=5.5), "requests_per_second", id="rps"),
        pytest.param(
            LimitsOverride(max_duration_minutes=61), "max_duration_minutes", id="duration"
        ),
        pytest.param(LimitsOverride(zap_threads_per_host=3), "zap_threads_per_host", id="threads"),
    ],
)
def test_narrow_limits_raises_config_error_when_override_exceeds_profile(
    override: LimitsOverride, field: str
) -> None:
    with pytest.raises(ConfigError, match=field):
        narrow_limits(base_limits(), override)


@pytest.mark.parametrize(
    "data",
    [
        {"requests_per_second": 0},
        {"requests_per_second": -1},
        {"requests_per_second": 1000},
        {"max_duration_minutes": 0},
        {"max_duration_minutes": 100000},
        {"zap_threads_per_host": 0},
        {"zap_threads_per_host": "2"},
        {"surprise": 1},
    ],
)
def test_limits_override_rejects_values_outside_hard_bounds(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        LimitsOverride.model_validate(data)
