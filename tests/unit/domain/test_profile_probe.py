"""Blocos aditivos do schema v1: `auth.csrf`, `probe` e `environment.verify_tls`."""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def profile(mutate: Any = None) -> ProductProfile:
    data = valid_profile_data()
    if mutate is not None:
        mutate(data)
    return ProductProfile.from_data(copy.deepcopy(data))


def message(mutate: Any) -> str:
    with pytest.raises(ConfigError) as info:
        profile(mutate)
    return info.value.message


def with_csrf(**csrf: object) -> Callable[[dict[str, Any]], None]:
    def apply(data: dict[str, Any]) -> None:
        data["scope"]["allow"][0]["methods"] = ["GET", "POST"]
        data["auth"]["csrf"] = {"fetch_path": "/api/csrf", **csrf}

    return apply


def test_profiles_without_the_new_blocks_keep_their_defaults() -> None:
    result = profile()

    assert result.auth.csrf is None
    assert result.probe.health_path is None
    assert result.probe.success.json_field_absent_or_not_equal is None
    assert result.environment.verify_tls is True


def test_csrf_defaults_match_spring_cookie_csrf_token_repository() -> None:
    csrf = profile(with_csrf()).auth.csrf

    assert csrf is not None
    assert (csrf.fetch_path, csrf.cookie_name, csrf.header_name) == (
        "/api/csrf",
        "XSRF-TOKEN",
        "X-XSRF-TOKEN",
    )
    assert csrf.methods == ("DELETE", "PATCH", "POST", "PUT")


def test_csrf_can_be_customised_and_methods_are_canonicalised() -> None:
    csrf = profile(
        with_csrf(cookie_name="CSRF", header_name="X-CSRF", methods=["POST", "POST", "DELETE"])
    ).auth.csrf

    assert csrf is not None
    assert (csrf.cookie_name, csrf.header_name, csrf.methods) == (
        "CSRF",
        "X-CSRF",
        ("DELETE", "POST"),
    )


def test_csrf_works_with_api_key_auth_too() -> None:
    def apply(data: dict[str, Any]) -> None:
        data["scope"]["allow"][0]["methods"] = ["GET", "POST"]
        data["auth"] = {
            "type": "api_key",
            "header_name": "X-API-Key",
            "accounts": [{"alias": "svc", "role": "s", "api_key": {"secret_ref": "env:ACME_K"}}],
            "csrf": {"fetch_path": "/api/csrf"},
        }

    assert profile(apply).auth.csrf is not None


@pytest.mark.parametrize(
    ("csrf", "fragment"),
    [
        ({"fetch_path": "/api/*"}, "auth.csrf.fetch_path"),
        ({"fetch_path": "api/csrf"}, "auth.csrf.fetch_path"),
        ({"fetch_path": "/api/csrf", "cookie_name": "a b"}, "auth.csrf.cookie_name"),
        ({"fetch_path": "/api/csrf", "header_name": "Host"}, "auth.csrf.header_name"),
        ({"fetch_path": "/api/csrf", "header_name": "x y"}, "auth.csrf.header_name"),
        ({"fetch_path": "/api/csrf", "methods": ["post"]}, "auth.csrf.methods"),
        ({"fetch_path": "/api/csrf", "methods": []}, "auth.csrf.methods"),
        ({"fetch_path": "/api/csrf", "extra": 1}, "auth.csrf.extra"),
        ({}, "auth.csrf.fetch_path"),
    ],
)
def test_invalid_csrf_blocks_are_rejected_with_the_field_path(
    csrf: dict[str, object], fragment: str
) -> None:
    def apply(data: dict[str, Any]) -> None:
        data["auth"]["csrf"] = csrf

    assert fragment in message(apply)


def test_the_csrf_fetch_path_must_be_inside_the_scope() -> None:
    def outside(data: dict[str, Any]) -> None:
        data["auth"]["csrf"] = {"fetch_path": "/publico/csrf"}

    def denied(data: dict[str, Any]) -> None:
        data["auth"]["csrf"] = {"fetch_path": "/api/admin/csrf"}

    assert "token CSRF" in message(outside)
    assert "token CSRF" in message(denied)


def test_success_rule_is_parsed_and_validated() -> None:
    def apply(data: dict[str, Any]) -> None:
        data["probe"] = {
            "success": {"json_field_absent_or_not_equal": {"field": "status", "value": "fail"}}
        }

    rule = profile(apply).probe.success.json_field_absent_or_not_equal

    assert rule is not None
    assert (rule.field, rule.value) == ("status", "fail")


@pytest.mark.parametrize(
    "rule",
    [
        {"field": "status"},
        {"field": "a b", "value": "x"},
        {"field": "status", "value": 1.5},
        {"field": "status", "value": [1]},
        {"field": "", "value": "x"},
        {"field": "status", "value": "x", "extra": 1},
    ],
)
def test_invalid_success_rules_are_rejected(rule: dict[str, object]) -> None:
    def apply(data: dict[str, Any]) -> None:
        data["probe"] = {"success": {"json_field_absent_or_not_equal": rule}}

    assert "probe.success.json_field_absent_or_not_equal" in message(apply)


def test_health_path_must_be_literal_and_inside_the_scope() -> None:
    def ok(data: dict[str, Any]) -> None:
        data["probe"] = {"health_path": "/api/saude"}

    def wildcard(data: dict[str, Any]) -> None:
        data["probe"] = {"health_path": "/api/*"}

    def outside(data: dict[str, Any]) -> None:
        data["probe"] = {"health_path": "/saude"}

    assert profile(ok).probe.health_path == "/api/saude"
    assert "probe.health_path" in message(wildcard)
    assert "probe.health_path" in message(outside)


def local_profile(verify_tls: object) -> Callable[[dict[str, Any]], None]:
    def apply(data: dict[str, Any]) -> None:
        data["environment"]["base_url"] = "http://vampi:5000"
        data["environment"]["verify_tls"] = verify_tls
        data["scope"]["allow"] = [
            {
                "host": "vampi",
                "scheme": "http",
                "port": 5000,
                "paths": ["/api/**"],
                "methods": ["GET", "POST"],
                "allow_local": True,
            }
        ]

    return apply


def test_tls_verification_can_be_disabled_only_for_local_hosts() -> None:
    assert profile(local_profile(False)).environment.verify_tls is False

    def public(data: dict[str, Any]) -> None:
        data["environment"]["verify_tls"] = False

    assert "verify_tls" in message(public)


@pytest.mark.parametrize("value", ["false", 0, None])
def test_verify_tls_must_be_a_real_boolean(value: object) -> None:
    assert "environment.verify_tls" in message(local_profile(value))
