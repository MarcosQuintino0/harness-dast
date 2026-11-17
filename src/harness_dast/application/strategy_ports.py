"""Portas consumidas pela capacidade strategy; assinaturas e docstrings preservadas."""

from typing import Protocol

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.strategy import Strategy, StrategyReferences


class StrategyCaptureStore(Protocol):
    """Armazenamento para captura explícita, sem substituir documentos existentes."""

    def read(self, product: str) -> dict[str, object] | None:
        """Lê estratégia ou devolve None quando ausente."""
        ...

    def check_references(self, product: str, references: StrategyReferences) -> None:
        """Confere a contenção das referências."""
        ...

    def read_dependencies(
        self, product: str, profile: ProductProfile
    ) -> tuple[bytes, bytes | None, bytes | None]:
        """Lê os documentos locais com tamanho e caminhos limitados."""
        ...

    def write_capture(self, product: str, output: str, strategy: Strategy) -> str:
        """Cria cópia exclusiva da estratégia validada."""
        ...
