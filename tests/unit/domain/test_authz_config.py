"""Bloco `authz` do perfil: padrões conservadores e entradas inválidas."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz_config import (
    CHECK_ORDER,
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

    assert config.enabled_checks() == (
        "horizontal",
        "excessive_data",
        "anonymous_access",
        "tampered_token",
        "mass_assignment",
    )
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


# --- escrita só com a carta (ADR 0038) -------------------------------------------------------


def test_writes_are_off_by_default_and_the_effective_methods_are_only_the_read_ones() -> None:
    config = AuthzConfig(vertical_methods=("GET", "HEAD", "POST", "PUT", "PATCH"))

    assert config.allow_writes is False
    assert config.effective_vertical_methods() == frozenset({"GET", "HEAD"})
    assert config.dropped_write_methods() == ("PATCH", "POST", "PUT")


def test_with_writes_allowed_every_declared_method_stays_in_the_plan() -> None:
    config = AuthzConfig(vertical_methods=("GET", "POST"), allow_writes=True)

    assert config.effective_vertical_methods() == frozenset({"GET", "POST"})
    assert config.dropped_write_methods() == ()


def test_the_default_methods_drop_nothing_without_writes() -> None:
    config = AuthzConfig()

    assert config.effective_vertical_methods() == frozenset({"GET", "HEAD"})
    assert config.dropped_write_methods() == ()


@pytest.mark.parametrize("value", ["sim", "true", 1, 0, None, ["x"]])
def test_allow_writes_accepts_only_a_real_boolean(value: Any) -> None:
    with pytest.raises(ValidationError):
        AuthzConfig(allow_writes=value)


def test_a_profile_with_allow_writes_true_is_loaded() -> None:
    data = valid_profile_data()
    data["authz"] = {"allow_writes": True}

    assert ProductProfile.from_data(data).authz.allow_writes is True


def test_a_profile_with_a_non_boolean_allow_writes_is_refused_as_a_config_error() -> None:
    data = valid_profile_data()
    data["authz"] = {"allow_writes": "sim"}

    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)


def test_the_check_order_puts_the_read_only_access_checks_before_vertical() -> None:
    assert CHECK_ORDER == (
        "horizontal",
        "excessive_data",
        "anonymous_access",
        "tampered_token",
        "vertical",
        "mass_assignment",
    )


def test_the_access_checks_can_be_disabled_and_requested_alone() -> None:
    config = AuthzConfig(disabled_checks=("tampered_token",))

    assert config.enabled_checks(("tampered_token", "anonymous_access")) == ("anonymous_access",)
    assert config.enabled_checks(("tampered_token",)) == ()


def test_unknown_check_name_in_disabled_checks_is_refused() -> None:
    with pytest.raises(ValidationError):
        AuthzConfig.model_validate({"disabled_checks": ["token_forjado"]})
