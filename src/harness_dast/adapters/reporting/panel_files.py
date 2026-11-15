"""Arquivos do painel da execução em `<runs_dir>/<run_id>/panel/` (implementa `PanelFiles`).

Lê `run.json` e `metrics.json` (pelo mesmo armazém dos outros arquivos de execução) e, de forma
tolerante, `agent-metrics.json` (tokens do agente), acha a
execução mais recente de um produto pelo nome da pasta e grava as páginas HTML de forma atômica
(arquivo temporário e `os.replace`). Só grava dentro da pasta `panel/` da execução: o nome da
página é conferido (sem barra, ponto-ponto nem letra fora de `[a-z0-9.-]`).
"""

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from harness_dast.adapters.reporting.run_files import MAX_FILE_BYTES, FileRunArtifacts
from harness_dast.domain.agent_metrics import AGENT_METRICS_SCHEMA_VERSION, AgentMetrics
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.panel_model import PANEL_DIR
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run import SLUG_PATTERN
from harness_dast.domain.run_metrics import RunMetrics
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult

AGENT_METRICS_FILE: Final = "agent-metrics.json"
_PAGE_NAME: Final = re.compile(r"[a-z0-9][a-z0-9-]*\.html")
_RUN_FOLDER: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-"
    rf"({SLUG_PATTERN})-[0-9a-f]{{4,8}}"
)


class FilePanelFiles:
    """Lê e grava, no sistema de arquivos, o que o painel precisa."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o armazém.

        Args:
            runs_dir: Pasta das execuções (`HDAST_RUNS_DIR`).
        """
        self._runs_dir = runs_dir
        self._artifacts = FileRunArtifacts(runs_dir)

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se não existe."""
        return self._optional(run_id, "manifest.json", self._artifacts.read_manifest)

    def read_probe(self, run_id: str) -> ProbeResult | None:
        """Lê `probe.json`; `None` se não existe."""
        return self._optional(run_id, "probe.json", self._artifacts.read_probe)

    def read_scan(self, run_id: str) -> ScanResult | None:
        """Lê `scan.json`; `None` se não existe."""
        return self._optional(run_id, "scan.json", self._artifacts.read_scan)

    def read_findings(self, run_id: str) -> FindingsReport | None:
        """Lê `findings.json`; `None` se não existe."""
        return self._optional(run_id, "findings.json", self._artifacts.read_findings)

    def read_authz(self, run_id: str) -> AuthzResult | None:
        """Lê `authz.json`; `None` se o estágio não rodou."""
        return self._artifacts.read_authz(run_id)

    def read_negative(self, run_id: str) -> NegativeResult | None:
        """Lê `negative.json`; `None` se o estágio não rodou."""
        return self._artifacts.read_negative(run_id)

    def read_summary(self, run_id: str) -> RunSummary | None:
        """Lê `run.json`; `None` se a execução não passou pelo `hdast run`."""
        return self._artifacts.read_summary(run_id)

    def read_metrics(self, run_id: str) -> RunMetrics | None:
        """Lê `metrics.json`; `None` se não existe."""
        return self._artifacts.read_metrics(run_id)

    def read_agent_metrics(self, run_id: str) -> AgentMetrics | None:
        """Lê `agent-metrics.json`; ausente, grande, inválido ou de outra versão vira `None`."""
        path = self._runs_dir / require_run_id(run_id) / AGENT_METRICS_FILE
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                return None
            found = AgentMetrics.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError):
            return None
        return found if found.schema_version == AGENT_METRICS_SCHEMA_VERSION else None

    def _exists(self, run_id: str, name: str) -> bool:
        return (self._runs_dir / require_run_id(run_id) / name).is_file()

    def _optional[T](self, run_id: str, name: str, read: Callable[[str], T]) -> T | None:
        return read(run_id) if self._exists(run_id, name) else None

    def latest_run_id(self, product: str) -> str | None:
        """Pasta mais recente cujo nome é um `run_id` do produto (o carimbo ordena por data)."""
        try:
            names = [entry.name for entry in self._runs_dir.iterdir() if entry.is_dir()]
        except OSError:
            return None
        mine = [
            name
            for name in names
            if (found := _RUN_FOLDER.fullmatch(name)) is not None and found.group(1) == product
        ]
        return max(mine) if mine else None

    def write_pages(self, run_id: str, pages: Mapping[str, str]) -> tuple[str, ...]:
        """Grava as páginas em `<run_id>/panel/` e devolve os caminhos relativos à execução."""
        directory = self._runs_dir / require_run_id(run_id) / PANEL_DIR
        written: list[str] = []
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for name, text in pages.items():
                if not _PAGE_NAME.fullmatch(name):
                    raise ConfigError(
                        "Nome de página do painel inválido.",
                        hint="É um erro do programa: relate ao mantenedor.",
                    )
                temporary = directory / f".{name}.tmp"
                temporary.write_text(text, encoding="utf-8", newline="\n")
                os.replace(temporary, directory / name)
                written.append(f"{PANEL_DIR}/{name}")
        except OSError:
            raise ConfigError(
                "Não foi possível gravar as páginas do painel.",
                hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
            ) from None
        return tuple(written)
