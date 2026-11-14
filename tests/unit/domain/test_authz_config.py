"""Bloco `authz` do perfil: padrões conservadores e entradas inválidas."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz_config import (
    DEFAULT_MASS_FIELDS,
    DEFAULT_VERTICAL_METHODS,
    AuthzConfig,
    normalize_field_name,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def test_the_defaults_are_conservative() -> None:
    config = AuthzConfig()

    assert config.public_operations == ()
    assert config.role_order == ()
    assert config.vertical_methods == DEFAULT_VERTICAL_METHODS == ("GET", "HEAD")
    assert [f.name for f in config.mass_assignment_fields] == ["role", "papel", "admin", "isAdmin"]
    assert config.mass_assignment_fields == DEFAULT_MASS_FIELDS


def test_a_profile_without_the_block_gets_the_defaults() -> None:
    profile = ProductProfile.from_data(valid_profile_data())

    assert profile.authz == AuthzConfig()


def test_a_profile_with_the_block_is_loaded() -> None:
    data = valid_profile_data()
    data["authz"] = {"public_operations": ["x"], "role_order": ["a", "b"]}

    profile = ProductProfile.from_data(data)

    assert profile.authz.role_order == ("a", "b")


@pytest.mark.parametrize(
    "change",
    [
        {"vertical_methods": ["DELETE"]},
        {"vertical_methods": []},
        {"vertical_methods": ["get"]},
        {"vertical_methods": ["TRACE"]},
        {"role_order": ["a", "a"]},
        {"role_order": ["com espaco"]},
        {"volatile_fields": ["com espaco"]},
        {"mass_assignment_fields": [{"name": "role", "value": "a"}] * 2},
        {"mass_assignment_fields": [{"name": "1ruim", "value": "a"}]},
        {"mass_assignment_fields": [{"name": "role", "value": ["lista"]}]},
        {"mass_assignment_fields": [{"name": "role", "value": 1.5}]},
        {"disabled_checks": ["inexistente"]},
        {"campo_desconhecido": 1},
    ],
)
def test_invalid_blocks_are_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AuthzConfig.model_validate(change)


def test_a_literal_secret_typed_in_the_wrong_place_is_not_echoed() -> None:
    with pytest.raises(ValidationError) as caught:
        AuthzConfig.model_validate({"role_order": ["SEGREDO-123", "SEGREDO-123"]})

    assert "SEGREDO-123" not in str(caught.value)


def test_checks_run_in_the_fixed_order_minus_the_disabled_ones() -> None:
    config = AuthzConfig(disabled_checks=("vertical",))

    assert config.enabled_checks() == ("horizontal", "excessive_data", "mass_assignment")
    assert config.enabled_checks(("mass_assignment", "horizontal")) == (
        "horizontal",
        "mass_assignment",
    )
    assert config.enabled_checks(("vertical",)) == ()


def test_volatile_names_are_normalized_and_include_the_defaults() -> None:
    names = AuthzConfig(volatile_fields=("versao_Do_Item",)).volatile_names()

    assert "versaodoitem" in names
    assert "requestid" in names


def test_normalizing_a_field_name_drops_separators_and_case() -> None:
    assert normalize_field_name("Request-ID") == normalize_field_name("request_id") == "requestid"


def test_a_public_operation_that_is_not_in_the_spec_is_a_config_error() -> None:
    config = AuthzConfig(public_operations=("lerCatalogo", "naoExiste"))

    with pytest.raises(ConfigError, match="naoExiste"):
        config.ensure_operations_exist(["lerCatalogo"])
    config.ensure_operations_exist(["lerCatalogo", "naoExiste"])
