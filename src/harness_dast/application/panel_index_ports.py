"""Portas dos índices e da página ao vivo do painel (ADR 0034).

Ficam à parte de `ports.py` (arquivo compartilhado), como as de `scan_ports.py`: a regra é a
mesma, porta declarada por quem a consome, sem regra de negócio. O adaptador dos arquivos é
`adapters/reporting/panel_index_files.py`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from harness_dast.domain.run_summary import RunSummary, StageName, StageRecord
from harness_dast.domain.traffic import TrafficSummary


@dataclass(frozen=True)
class RunFolder:
    """Uma pasta de execução em `runs/`.

    Attributes:
        run_id: Nome da pasta.
        product: Slug do produto, tirado do nome da pasta.
    """

    run_id: str
    product: str


class PanelIndexFiles(Protocol):
    """Pasta das execuções vista pelos índices: lista as execuções e grava os índices."""

    def list_runs(self) -> tuple[RunFolder, ...]:
        """Pastas cujo nome é um `run_id` (de qualquer produto); vazio se `runs/` não existe."""
        ...

    def has_panel(self, run_id: str) -> bool:
        """Se o Resumo do painel da execução (`panel/summary.html`) existe."""
        ...

    def write_index(self, name: str, text: str) -> str:
        """Grava um índice (`index.html` ou `history-<produto>.html`) em `runs/`, de forma atômica.

        Returns:
            O nome gravado.

        Raises:
            ConfigError: Nome inválido ou falha de escrita.
        """
        ...


class RunLive(Protocol):
    """O que o `run` avisa à página ao vivo (ADR 0034).

    Garante: nunca levanta erro do harness e nunca espera por I/O além de uma gravação local.
    A página é secundária: se não puder ser gravada, o erro vai para o log e o `run` segue.
    """

    def stage_started(
        self,
        product: str,
        run_id: str,
        stage: StageName,
        records: Sequence[StageRecord],
        *,
        started: datetime,
        authz: bool,
    ) -> None:
        """A etapa começou (`records` traz as que já terminaram)."""
        ...

    def run_finished(self, product: str, run_id: str, summary: RunSummary) -> None:
        """O `run` acabou: regrava a página uma última vez, sem recarga automática."""
        ...


class ScanLive(Protocol):
    """O que a varredura avisa à página ao vivo, uma vez por função.

    Garante: nunca levanta erro do harness (mesma regra de `RunLive`).
    """

    def scan_progress(
        self,
        run_id: str,
        done: int,
        total: int,
        operation_id: str | None,
        traffic: TrafficSummary | None,
    ) -> None:
        """`done` de `total` funções varridas; `operation_id` é a próxima (ou `None` no fim)."""
        ...
