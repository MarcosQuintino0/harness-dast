"""Portas consumidas pela capacidade wait; assinaturas e docstrings preservadas."""

from typing import Protocol

from harness_dast.domain.wait import WaitResult


class WaitReader(Protocol):
    """Fornece uma observação validada da execução."""

    def read(self, run_id: str) -> WaitResult:
        """Lê uma observação ou informa erro de configuração."""
        ...
