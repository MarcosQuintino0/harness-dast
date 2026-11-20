"""Portas consumidas pelo `hdast setup` (ADR 0114)."""

from typing import Protocol


class AppliedDefaultsReader(Protocol):
    """Lê do perfil gerado da carta quais padrões mínimos da CLI foram aplicados."""

    def read(self, product: str) -> tuple[str, ...]:
        """Devolve `campo = valor` de cada padrão aplicado; vazio se não houve.

        Raises:
            ConfigError: Produto inválido ou `target.yml` ilegível.
        """
        ...


class SetupNotifier(Protocol):
    """Canal por onde o `setup` fala com a pessoa entre um passo e outro."""

    def say(self, text: str) -> None:
        """Mostra uma linha à pessoa; nunca recebe valor de segredo."""
        ...
