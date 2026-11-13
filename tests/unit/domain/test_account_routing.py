"""Roteamento de contas por operação (`auth.default_account` e `auth.account_map`)."""

from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from tests.fakes.rig import profile_data


def profile(**auth: Any) -> ProductProfile:
    data = profile_data()
    data["auth"]["accounts"].append(
        {
            "alias": "user_b",
            "role": "outro",
            "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
            "password": {"secret_ref": "env:ACME_USER_B_SENHA"},
        }
    )
    data["auth"].update(auth)
    return ProductProfile.from_data(data)


def test_without_routing_every_operation_uses_the_first_account() -> None:
    assert profile().account_for("qualquer", "GET", "/api/x") == "user_a"


def test_default_account_replaces_the_first_one() -> None:
    assert profile(default_account="user_b").account_for("qualquer", "GET", "/api/x") == "user_b"


def test_the_first_matching_rule_wins() -> None:
    chosen = profile(
        account_map=[
            {"account": "user_b", "operations": ["criar"]},
            {"account": "user_a", "operations": ["criar"]},
        ]
    )

    assert chosen.account_for("criar", "POST", "/api/x") == "user_b"


def test_a_path_rule_treats_openapi_placeholders_as_one_segment() -> None:
    chosen = profile(account_map=[{"account": "user_b", "path": "/api/pacientes/*/receitas"}])

    assert chosen.account_for("op", "GET", "/api/pacientes/{id}/receitas") == "user_b"
    assert chosen.account_for("op", "GET", "/api/pacientes/{id}") == "user_a"


def test_a_double_star_path_rule_matches_the_root_of_the_prefix() -> None:
    chosen = profile(account_map=[{"account": "user_b", "path": "/api/receitas/**"}])

    assert chosen.account_for("op", "GET", "/api/receitas") == "user_b"


def test_methods_narrow_a_path_rule() -> None:
    chosen = profile(account_map=[{"account": "user_b", "path": "/api/**", "methods": ["POST"]}])

    assert chosen.account_for("op", "POST", "/api/x") == "user_b"
    assert chosen.account_for("op", "GET", "/api/x") == "user_a"


def test_all_declared_criteria_must_match() -> None:
    chosen = profile(
        account_map=[{"account": "user_b", "operations": ["criar"], "path": "/api/outro"}]
    )

    assert chosen.account_for("criar", "POST", "/api/x") == "user_a"


def test_the_pinned_account_overrides_the_map() -> None:
    chosen = profile(account_map=[{"account": "user_b", "operations": ["criar"]}])

    assert chosen.account_for("criar", "POST", "/api/x", pinned="user_a") == "user_a"


def test_a_rule_naming_an_unknown_account_is_rejected_with_the_valid_ones() -> None:
    with pytest.raises(ConfigError, match="user_z"):
        profile(account_map=[{"account": "user_z", "operations": ["criar"]}])


def test_a_default_account_that_does_not_exist_is_rejected() -> None:
    with pytest.raises(ConfigError, match="user_z"):
        profile(default_account="user_z")


@pytest.mark.parametrize(
    "rule",
    [
        {"account": "user_b"},
        {"account": "user_b", "methods": ["GET"]},
        {"account": "user_b", "path": "api/sem-barra"},
        {"account": "user_b", "path": "/api/**", "methods": ["get"]},
        {"account": "user_b", "operations": ["a"], "extra": 1},
    ],
)
def test_malformed_rules_are_rejected(rule: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        profile(account_map=[rule])


def test_api_key_auth_accepts_the_same_routing() -> None:
    data = profile_data()
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-Api-Key",
        "accounts": [
            {"alias": "chave_a", "role": "x", "api_key": {"secret_ref": "env:A"}},
            {"alias": "chave_b", "role": "y", "api_key": {"secret_ref": "env:B"}},
        ],
        "account_map": [{"account": "chave_b", "operations": ["criar"]}],
    }

    chosen = ProductProfile.from_data(data)

    assert chosen.account_for("criar", "POST", "/api/x") == "chave_b"
