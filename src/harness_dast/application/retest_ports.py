"""Portas do caso de uso `retestar` (ADR 0112)."""

from typing import Protocol

from harness_dast.application.run import RunRequest, RunResult
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.retest import RetestReport


class RunStage(Protocol):
    """O pipeline do `run`, reaproveitado com todos os controles dele."""

    def execute(self, request: RunRequest) -> RunResult:
        """Roda o pipeline completo e grava `run.json`."""
        ...


class RetestArtifacts(Protocol):
    """Arquivos que o reteste lê (`findings.json`) e grava (`retest.json`)."""

    def read_findings(self, run_id: str) -> FindingsReport:
        """Lê `findings.json` de uma execução.

        Raises:
            ConfigError: Execução ou arquivo ausente, ilegível ou inválido.
        """
        ...

    def write_retest(self, run_id: str, report: RetestReport) -> str:
        """Grava `retest.json` na pasta da execução e devolve o nome do arquivo.

        Raises:
            ConfigError: A pasta da execução não pôde ser escrita.
        """
        ...
