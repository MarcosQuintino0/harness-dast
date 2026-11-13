"""Destinos do relatório: `findings.json`, `report.md` e `report.html` (implementam `ReportSink`).

Cada destino grava um arquivo na pasta da execução, de forma atômica. O conteúdo vem pronto do
domínio (`FindingsReport` e `render_markdown`); aqui só se escolhe o formato e o arquivo.
"""

import os
from pathlib import Path
from typing import Final

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_markdown import render_markdown
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.run_ref import require_run_id

FINDINGS_FILE: Final = "findings.json"
REPORT_FILE: Final = "report.md"
HTML_FILE: Final = "report.html"


def _write_atomic(runs_dir: Path, run_id: str, name: str, text: str) -> str:
    directory = runs_dir / require_run_id(run_id)
    temporary = directory / f".{name}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, directory / name)
    except OSError:
        raise ConfigError(
            f"Não foi possível gravar {name} da execução.",
            hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
        ) from None
    return name


class JsonFindingsSink:
    """Grava `findings.json` (esquema versionado em `docs/reference/finding-schema.md`)."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o destino.

        Args:
            runs_dir: Pasta das execuções.
        """
        self._runs_dir = runs_dir

    def write(self, run_id: str, report: FindingsReport) -> str:
        """Grava o relatório em JSON e devolve o nome do arquivo."""
        text = report.model_dump_json(indent=2) + "\n"
        return _write_atomic(self._runs_dir, run_id, FINDINGS_FILE, text)


class MarkdownReportSink:
    """Grava `report.md` (português, seguro para renderizar)."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o destino.

        Args:
            runs_dir: Pasta das execuções.
        """
        self._runs_dir = runs_dir

    def write(self, run_id: str, report: FindingsReport) -> str:
        """Grava o relatório em Markdown e devolve o nome do arquivo."""
        return _write_atomic(self._runs_dir, run_id, REPORT_FILE, render_markdown(report))


class HtmlReportSink:
    """Grava `report.html` (página única e autocontida, sem JavaScript)."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o destino.

        Args:
            runs_dir: Pasta das execuções.
        """
        self._runs_dir = runs_dir

    def write(self, run_id: str, report: FindingsReport) -> str:
        """Grava o relatório em HTML e devolve o nome do arquivo."""
        return _write_atomic(self._runs_dir, run_id, HTML_FILE, render_html(report))
