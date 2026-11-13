"""Provedor de segredos por variável de ambiente."""

import pytest

from harness_dast.adapters.secrets.env_provider import EnvSecretProvider
from harness_dast.domain.secret_ref import SecretRef


def ref(name: str) -> SecretRef:
    return SecretRef(secret_ref=f"env:{name}")


def test_the_value_is_read_from_the_given_environment() -> None:
    provider = EnvSecretProvider({"AGENDA_SENHA": "s3nh4 com espaço"})

    assert provider.resolve(ref("AGENDA_SENHA")) == "s3nh4 com espaço"


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_missing_empty_or_blank_values_resolve_to_none(value: str | None) -> None:
    environ = {} if value is None else {"AGENDA_SENHA": value}

    assert EnvSecretProvider(environ).resolve(ref("AGENDA_SENHA")) is None


def test_only_the_referenced_variable_is_read() -> None:
    provider = EnvSecretProvider({"A": "1", "B": "2"})

    assert provider.resolve(ref("B")) == "2"
    assert provider.resolve(ref("C")) is None
