"""Traduz falha do diário em parada que preserva o resultado parcial do estágio."""

from typing import Literal

from harness_dast.application.common_ports import MutationJournal
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.mutation_snapshot import MutationSnapshot


class MutationJournalBlocked(ExternalToolError):
    """O diário não confirmou a intenção ou o resultado; a operação não deve ser repetida."""


def begin_mutation(
    journal: MutationJournal, key: str, snapshot: MutationSnapshot | None = None
) -> None:
    """Reserva a intenção antes de enviar ou interrompe sem liberar a pendência."""
    try:
        if snapshot is None:
            journal.begin(key, "unknown")
        else:
            state: Literal["present", "unknown"] = (
                "present" if snapshot.source == "observed" else "unknown"
            )
            journal.begin(key, state, snapshot)
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
