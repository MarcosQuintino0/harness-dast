"""Portas consumidas pela capacidade scope_approval; assinaturas e docstrings preservadas."""

from typing import Protocol


class ApprovalPrompt(Protocol):
    """Confirmação de uma PESSOA, em terminal, diante do resumo dos blocos de proteção."""

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        """Mostra o resumo (e o que mudou desde a aprovação anterior) e pergunta.

        Returns:
            `True` só se a pessoa digitou exatamente o nome do produto.
        """
        ...
