"""Traduz falha do diário em parada que preserva o resultado parcial do estágio."""

from typing import Literal

from harness_dast.application.ports import MutationJournal
from harness_dast.domain.errors import ConfigError, ExternalToolError


class MutationJournalBlocked(ExternalToolError):
    """O diário não confirmou a intenção ou o resultado; a operação não deve ser repetida."""


def begin_mutation(journal: MutationJournal, key: str) -> None:
    """Reserva a intenção antes de enviar ou interrompe sem liberar a pendência."""
    try:
        journal.begin(key, "unknown")
    except ConfigError as error:
        raise MutationJournalBlocked(error.message, hint=error.hint) from error


def finish_mutation(
    journal: MutationJournal, key: str, outcome: Literal["failed", "observed"]
) -> None:
    """Registra o desfecho observado ou interrompe sem repetir a mutação."""
    try:
        journal.finish(key, outcome)
    except ConfigError as error:
        raise MutationJournalBlocked(error.message, hint=error.hint) from error
