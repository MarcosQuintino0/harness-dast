"""Leitor de carta em memória, com o comportamento da porta `LetterReader`."""

from collections.abc import Mapping
from pathlib import Path

from harness_dast.domain.errors import ConfigError


class InMemoryLetterReader:
    """Devolve as cartas registradas por nome de arquivo; as demais não existem."""

    def __init__(self, letters: Mapping[str, Mapping[str, object]]) -> None:
        self._letters = letters
        self.reads: list[str] = []

    def read(self, path: Path) -> Mapping[str, object]:
        self.reads.append(path.name)
        if path.name not in self._letters:
            raise ConfigError(f"A carta {path.name} não foi encontrada.")
        return self._letters[path.name]
