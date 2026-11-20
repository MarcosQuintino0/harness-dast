"""Portas de artefatos para a confirma??o."""

from typing import Protocol

from harness_dast.application.nuclei import NucleiRequest
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.verification import VerificationFile


class ConfirmationArtifacts(Protocol):
    """Leitura validada dos artefatos da execução existente."""

    def read_probe(self, run_id: str) -> ProbeResult:
        """Lê resultado do probe."""
        ...

    def read_scan(self, run_id: str) -> ScanResult:
        """Lê resultado do scan."""
        ...

    def read_exchanges(self, run_id: str) -> ExchangeLog:
        """Lê sementes do probe."""
        ...

    def read_findings(self, run_id: str) -> FindingsReport:
        """Lê achados do relatório."""
        ...

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê sequência anterior da auditoria."""
        ...


class NucleiReproducer(Protocol):
    """Caso de uso do Nuclei, que o `confirm` usa para repetir o modelo de um achado."""

    def execute(self, request: NucleiRequest) -> NucleiResult:
        """Roda o Nuclei só com os modelos pedidos e devolve o resultado limpo.

        Raises:
            HarnessError: Perfil, janela, cerca ou motor impedem a execução.
        """
        ...


class ConfirmationStore(Protocol):
    """Persistência redigida e atômica do envelope da verificação."""

    def read(self) -> VerificationFile:
        """Lê e valida resultado existente."""
        ...

    def write(self, verification: VerificationFile) -> None:
        """Redige e grava resultado incremental."""
        ...
