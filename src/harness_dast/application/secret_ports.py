"""Portas consumidas pela capacidade secret; assinaturas e docstrings preservadas."""

from typing import Protocol


class CredentialStore(Protocol):
    """Cofre de credenciais do sistema operacional (`secret_ref: keyring:NOME`, ADR 0030).

    Os três métodos levantam `SecretBackendError` se o cofre não está utilizável; nenhum
    registra nem inclui o valor em exceção.
    """

    def read(self, name: str) -> str | None:
        """Devolve o valor guardado sob `name`, ou `None` se não existe ou está vazio."""
        ...

    def write(self, name: str, value: str) -> None:
        """Guarda `value` sob `name`, substituindo o que houver."""
        ...

    def remove(self, name: str) -> bool:
        """Apaga `name`. Devolve `False` se não existia."""
        ...


class SecretPrompt(Protocol):
    """Prompt de terminal para a PESSOA gerir o cofre; o valor nunca é mostrado."""

    def read_value(self, name: str) -> str:
        """Lê o valor de `name` por prompt oculto, pedindo duas vezes (confirmação)."""
        ...

    def confirm_removal(self, name: str) -> bool:
        """Pede que a pessoa digite `name` para confirmar; `True` só se digitar igual."""
        ...
