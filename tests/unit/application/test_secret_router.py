"""Roteador de segredos: `env:` pelo ambiente, `keyring:` pelo cofre, nunca um no lugar do outro."""

import pytest

from harness_dast.application.secret_router import RoutingSecretProvider
from harness_dast.domain.errors import SecretBackendError
from harness_dast.domain.secret_ref import SecretRef
from tests.fakes.credential_store import InMemoryCredentialStore
from tests.fakes.probe_ports import DictSecretProvider


def ref(text: str) -> SecretRef:
    return SecretRef(secret_ref=text)


def test_env_reference_is_read_from_the_environment_and_never_touches_the_vault() -> None:
    store = InMemoryCredentialStore(broken=True)
    router = RoutingSecretProvider(DictSecretProvider({"A": "do-ambiente"}), store)

    assert router.resolve(ref("env:A")) == "do-ambiente"


def test_keyring_reference_is_read_from_the_vault() -> None:
    router = RoutingSecretProvider(DictSecretProvider({}), InMemoryCredentialStore({"A": "cofre"}))

    assert router.resolve(ref("keyring:A")) == "cofre"


def test_keyring_reference_never_falls_back_to_a_variable_of_the_same_name() -> None:
    router = RoutingSecretProvider(
        DictSecretProvider({"A": "do-ambiente"}), InMemoryCredentialStore()
    )

    assert router.resolve(ref("keyring:A")) is None


def test_env_reference_never_falls_back_to_the_vault_of_the_same_name() -> None:
    router = RoutingSecretProvider(DictSecretProvider({}), InMemoryCredentialStore({"A": "cofre"}))

    assert router.resolve(ref("env:A")) is None


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_blank_vault_value_resolves_to_none(value: str) -> None:
    router = RoutingSecretProvider(DictSecretProvider({}), InMemoryCredentialStore({"A": value}))

    assert router.resolve(ref("keyring:A")) is None


def test_broken_vault_raises_instead_of_resolving_elsewhere() -> None:
    router = RoutingSecretProvider(
        DictSecretProvider({"A": "do-ambiente"}), InMemoryCredentialStore(broken=True)
    )

    with pytest.raises(SecretBackendError):
        router.resolve(ref("keyring:A"))
