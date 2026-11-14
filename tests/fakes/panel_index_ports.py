"""Falsos dos índices e da página ao vivo do painel (ADR 0034)."""

from collections.abc import Mapping, Sequence
from datetime import datetime

from harness_dast.application.panel_index_ports import RunFolder
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run_summary import RunSummary, StageName, StageRecord
from harness_dast.domain.traffic import TrafficSummary
from tests.fakes.panel_ports import FakePanelFiles


class FakeIndexFiles:
    """`PanelIndexFiles` em memória: pastas dadas pelo teste e índices gravados num dicionário."""

    def __init__(self) -> None:
        self.folders: list[RunFolder] = []
        self.panels: set[str] = set()
        self.written: dict[str, str] = {}
        self.write_error: ConfigError | None = None

    def add(self, run_id: str, product: str, *, panel: bool = False) -> None:
        self.folders.append(RunFolder(run_id=run_id, product=product))
        if panel:
            self.panels.add(run_id)

    def list_runs(self) -> tuple[RunFolder, ...]:
        return tuple(self.folders)

    def has_panel(self, run_id: str) -> bool:
        return run_id in self.panels

    def write_index(self, name: str, text: str) -> str:
        if self.write_error is not None:
            raise self.write_error
        self.written[name] = text
        return name


class BreakableFiles(FakePanelFiles):
    """`FakePanelFiles` em que certas execuções têm todos os arquivos ilegíveis, e que lembra
    cada página gravada, na ordem (a página ao vivo é regravada várias vezes)."""

    def __init__(self) -> None:
        super().__init__()
        self.broken: set[str] = set()
        self.history: list[tuple[str, str, str]] = []

    def _read[T](self, store: Mapping[str, T], name: str, run_id: str) -> T | None:
        if run_id in self.broken:
            raise ConfigError(f"O arquivo {name} da execução está ilegível.")
        return super()._read(store, name, run_id)

    def write_pages(self, run_id: str, pages: Mapping[str, str]) -> tuple[str, ...]:
        if self.write_error is not None:
            raise self.write_error
        self.history += [(run_id, name, text) for name, text in pages.items()]
        return tuple(f"panel/{name}" for name in pages)

    def live_pages(self, run_id: str) -> list[str]:
        return [text for rid, name, text in self.history if rid == run_id and name == "live.html"]


class RecordingLive:
    """`RunLive` e `ScanLive` falsos: guardam o que receberam."""

    def __init__(self) -> None:
        self.stages: list[StageName] = []
        self.progress: list[tuple[int, int, str | None]] = []
        self.finished: list[RunSummary] = []

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
        self.stages.append(stage)

    def run_finished(self, product: str, run_id: str, summary: RunSummary) -> None:
        self.finished.append(summary)

    def scan_progress(
        self,
        run_id: str,
        done: int,
        total: int,
        operation_id: str | None,
        traffic: TrafficSummary | None,
    ) -> None:
        self.progress.append((done, total, operation_id))
