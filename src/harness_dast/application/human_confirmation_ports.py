"""Portas de persistência e interação da confirmação humana."""

from typing import Protocol

from harness_dast.domain.human_confirmation import HumanConfirmation, HumanConfirmations
from harness_dast.domain.report.model import FindingsReport


class HumanConfirmationStore(Protocol):
    """Armazena registros aditivos por execução."""

    def read(self, product: str, run_id: str) -> HumanConfirmations | None:
        """Lê registros validados ou devolve None se ausentes; falha em corrupção."""
        ...

    def append(self, product: str, run_id: str, entry: HumanConfirmation) -> None:
        """Acrescenta sem perder registros anteriores ou falha fechada."""
        ...


class HumanFindingReader(Protocol):
    """Lê o relatório existente da execução."""

    def read_findings(self, run_id: str) -> FindingsReport:
        """Devolve relatório validado ou falha."""
        ...


class HumanConfirmationPrompt(Protocol):
    """Obtém declaração e consentimento por interação."""

    def ask(self, fingerprint: str) -> tuple[str, str] | None:
        """Devolve pessoa e observação, ou None se cancelado."""
        ...
