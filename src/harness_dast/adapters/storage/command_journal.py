"""Diário de comandos em arquivos JSONL por produto (implementa `CommandJournalStore`, ADR 0033).

Fica em `<pasta de estado>/journal/<produto>.jsonl`, na mesma pasta de estado da pilha
(`HDAST_STATE_DIR`; veja `stack_state.default_state_dir`), nunca dentro do repositório nem de
`runs/`. Comandos sem produto vão para `_sem-produto.jsonl`. Só acréscimo: cada linha é uma
`JournalEntry` com `schema_version`. Pasta 0700 e arquivo 0600 no POSIX; no Windows vale a ACL
herdada da pasta de estado. O nome do arquivo sai de `journal_file_stem`, que só aceita slug:
um produto nunca escapa da pasta.
"""

import os
import sys
from pathlib import Path

from harness_dast.domain.command_journal import (
    JournalEntry,
    JournalLoad,
    journal_file_stem,
    parse_journal_lines,
)
from harness_dast.domain.errors import ConfigError

JOURNAL_DIR_NAME = "journal"
_DIR_MODE = 0o700
_FILE_MODE = 0o600


class FileCommandJournalStore:
    """Grava e lê o diário no sistema de arquivos."""

    def __init__(self, state_dir: Path) -> None:
        """Cria o armazém (nada é criado até a primeira escrita).

        Args:
            state_dir: Pasta de estado da ferramenta.
        """
        self._directory = state_dir / JOURNAL_DIR_NAME

    def location(self, product: str | None) -> Path:
        """Caminho do arquivo do diário do produto."""
        return self._directory / f"{journal_file_stem(product)}.jsonl"

    def append(self, product: str | None, entry: JournalEntry) -> None:
        """Acrescenta uma linha ao diário do produto."""
        line = entry.model_dump_json() + "\n"
        path = self.location(product)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            if sys.platform != "win32":
                self._directory.chmod(_DIR_MODE)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
            with os.fdopen(descriptor, "ab") as handle:
                handle.write(line.encode("utf-8"))
        except OSError:
            raise ConfigError(
                "Não foi possível gravar o diário de comandos.",
                hint="Confira HDAST_STATE_DIR, o espaço em disco e a permissão de escrita.",
            ) from None

    def load(self, product: str | None) -> JournalLoad:
        """Lê o diário; arquivo ausente vale por diário vazio."""
        path = self.location(product)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return JournalLoad(entries=(), skipped_lines=0)
        except OSError:
            raise ConfigError(
                "Não foi possível ler o diário de comandos.",
                hint="Confira HDAST_STATE_DIR e a permissão de leitura da pasta journal.",
            ) from None
        return parse_journal_lines(raw.decode("utf-8", errors="replace").splitlines())
