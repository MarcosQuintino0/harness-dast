"""Resolve `secret_ref` pela origem certa: variável de ambiente ou cofre do sistema."""

from harness_dast.application.ports import CredentialStore, SecretProvider
from harness_dast.domain.secret_ref import SecretRef


class RoutingSecretProvider:
    """Implementa `SecretProvider` despachando por `SecretRef.kind` (ADR 0030).

    `env:` vai ao provedor de ambiente e `keyring:` ao cofre; nunca um cai no outro. Se o
    cofre não está utilizável, `SecretBackendError` sobe: não há desvio silencioso.
    """

    def __init__(self, env: SecretProvider, store: CredentialStore) -> None:
        """Cria o roteador.

        Args:
            env: Provedor de `env:NOME`.
            store: Cofre de `keyring:NOME` (só é tocado quando alguma referência o cita).
        """
        self._env = env
        self._store = store

    def resolve(self, ref: SecretRef) -> str | None:
        """Devolve o valor, ou `None` se ausente ou só com espaços.

        Raises:
            SecretBackendError: A referência é `keyring:` e o cofre não está utilizável.
        """
        if ref.kind == "env":
            return self._env.resolve(ref)
        value = self._store.read(ref.name)
        if value is None or not value.strip():
            return None
        return value
