"""Pasta `runs/` vista pelos índices do painel (implementa `PanelIndexFiles`).

Lista as pastas cujo nome é um `run_id` e grava `index.html` e `history-<produto>.html` direto em
`runs/`, de forma atômica (arquivo temporário e `os.replace`). Só grava esses dois formatos de
nome: o nome é conferido (sem barra, ponto-ponto nem letra fora de `[a-z0-9.-]`), então nada
sai de `runs/`.
"""

import os
import re
from pathlib import Path
from typing import Final

from harness_dast.application.panel_index_ports import RunFolder
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.panel.model import HISTORY_PREFIX, INDEX_FILE, PANEL_DIR
from harness_dast.domain.run import SLUG_PATTERN

_RUN_FOLDER: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-"
    rf"({SLUG_PATTERN})-[0-9a-f]{{4,8}}"
)
_INDEX_NAME: Final = re.compile(
    rf"{re.escape(INDEX_FILE)}|{re.escape(HISTORY_PREFIX)}{SLUG_PATTERN}\.html"
)


class FilePanelIndexFiles:
    """Lê a lista de execuções e grava os índices no sistema de arquivos."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o armazém.

        Args:
            runs_dir: Pasta das execuções (`HDAST_RUNS_DIR`).
        """
        self._runs_dir = runs_dir

    def list_runs(self) -> tuple[RunFolder, ...]:
        """Pastas cujo nome é um `run_id`, de qualquer produto (a ordem fica para quem monta)."""
        try:
            entries = [item for item in self._runs_dir.iterdir() if item.is_dir()]
        except OSError:
            return ()
        found: list[RunFolder] = []
        for entry in entries:
            match = _RUN_FOLDER.fullmatch(entry.name)
            if match is not None:
                found.append(RunFolder(run_id=entry.name, product=match.group(1)))
        return tuple(sorted(found, key=lambda item: item.run_id))

    def has_panel(self, run_id: str) -> bool:
        """Se `panel/summary.html` existe na pasta da execução."""
        if _RUN_FOLDER.fullmatch(run_id) is None:
            return False
        return (self._runs_dir / run_id / PANEL_DIR / "summary.html").is_file()

    def write_index(self, name: str, text: str) -> str:
        """Grava o índice em `runs/` e devolve o nome."""
        if not _INDEX_NAME.fullmatch(name):
            raise ConfigError(
                "Nome de índice do painel inválido.",
                hint="É um erro do programa: relate ao mantenedor.",
            )
        try:
            self._runs_dir.mkdir(parents=True, exist_ok=True)
            temporary = self._runs_dir / f".{name}.tmp"
            temporary.write_text(text, encoding="utf-8", newline="\n")
            os.replace(temporary, self._runs_dir / name)
        except OSError:
            raise ConfigError(
                "Não foi possível gravar os índices do painel.",
                hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
            ) from None
        return name
