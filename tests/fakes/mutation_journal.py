"""Diário de mutações em memória: guarda as chaves pendentes e os desfechos."""

from typing import Literal

from harness_dast.domain.knowledge_mutation import MutationMetadata, MutationPending
from harness_dast.domain.mutation_snapshot import MutationSnapshot


class MemoryMutationJournal:
    """Cumpre `MutationJournal`: pendência impede repetição; `finish` libera a chave."""

    def __init__(self) -> None:
        self.pending: set[str] = set()
        self.began: list[str] = []
        self.outcomes: list[str] = []

    def begin(
        self,
        key: str,
        previous_state: Literal["absent", "present", "unknown"],
        snapshot: MutationSnapshot | None = None,
        metadata: MutationMetadata | None = None,
    ) -> None:
        if key in self.pending:
            raise MutationPending("Mutação pendente")
        self.pending.add(key)
        self.began.append(key)

    def finish(self, key: str, outcome: Literal["succeeded", "failed", "observed"]) -> None:
        self.pending.discard(key)
        self.outcomes.append(outcome)
