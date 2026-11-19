"""Leitor de caminhos do OpenAPI em memória, com o comportamento da porta `SpecPathReader`."""

from pathlib import Path

from harness_dast.domain.errors import ConfigError


class InMemorySpecPaths:
    """Devolve os caminhos registrados por nome de arquivo; os demais não existem."""

    def __init__(self, specs: dict[str, tuple[str, ...]]) -> None:
        self._specs = specs
        self.reads: list[tuple[Path, str]] = []

    def read_paths(self, base_dir: Path, relative: str) -> tuple[str, ...]:
        self.reads.append((base_dir, relative))
        if relative not in self._specs:
            raise ConfigError("O OpenAPI não foi encontrado.", hint="Ponha-o ao lado da carta.")
        return self._specs[relative]
