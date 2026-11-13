"""Montagem dos provedores de segredo da CLI: ambiente e cofre do sistema (ADR 0030)."""

import keyring
from keyring.backend import KeyringBackend

from harness_dast.adapters.secrets.env_provider import EnvSecretProvider
from harness_dast.adapters.secrets.keyring_store import KeyringCredentialStore
from harness_dast.application.ports import CredentialStore
from harness_dast.application.secret_router import RoutingSecretProvider
from harness_dast.cli.stack_composition import layered_environ


def default_backend() -> KeyringBackend:
    """Backend que o `keyring` escolheria na máquina (validado depois pelo adaptador)."""
    return keyring.get_keyring()


def build_credential_store() -> CredentialStore:
    """Cofre do sistema; o backend só é aberto no primeiro uso."""
    return KeyringCredentialStore(default_backend)


def build_secret_provider() -> RoutingSecretProvider:
    """Provedor de `secret_ref`: `env:` pelo ambiente e `keyring:` pelo cofre.

    Raises:
        ConfigError: Arquivo de estado da pilha inválido (ele completa o ambiente).
    """
    return RoutingSecretProvider(EnvSecretProvider(layered_environ()), build_credential_store())
