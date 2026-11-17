"""Portas consumidas pela capacidade knowledge; assinaturas e docstrings preservadas."""

from typing import Protocol

from harness_dast.domain.knowledge_evidence import KnowledgeRunEvidence


class KnowledgeRunStore(Protocol):
    """Lê artefatos de uma execução sem persistir seus conteúdos no conhecimento."""

    def read(self, run_id: str) -> KnowledgeRunEvidence:
        """Valida e resume os artefatos identificados pela execução."""
        ...


class KnowledgeStore(Protocol):
    """Armazena documento de conhecimento sem conceder autoridade."""

    def read(self, product: str) -> dict[str, object] | None:
        """Lê conhecimento ativo, quando presente."""
        ...

    def write_capture(self, product: str, knowledge: object) -> str:
        """Grava cópia separada sem substituir arquivo existente."""
        ...
