"""Porta do teste negativo: os arquivos da execução que ele lê e grava.

Fica aqui, e não em `ports.py`, pelo mesmo motivo de `authz_ports.py`: `ports.py` é compartilhado
e a regra é a mesma (porta declarada por quem a consome, sem regra de negócio). O adaptador é
`adapters/reporting/run_files.py`.
"""

from typing import Protocol

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult


class NegativeArtifacts(Protocol):
    """Arquivos de uma execução que o `negative` lê (do `probe`) e grava (`negative.json`)."""

    def read_probe(self, run_id: str) -> ProbeResult:
        """Lê `probe.json`.

        Raises:
            ConfigError: Arquivo ausente, ilegível ou inválido.
        """
        ...

    def read_exchanges(self, run_id: str) -> ExchangeLog:
        """Lê `exchanges.json`.

        Raises:
            ConfigError: Arquivo ausente (o `probe` não rodou com envio), ilegível ou inválido.
        """
        ...

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê `audit.jsonl` (para continuar a numeração).

        Raises:
            ConfigError: Arquivo ausente, ilegível ou inválido.
        """
        ...

    def write_negative(self, run_id: str, result: NegativeResult) -> None:
        """Grava `negative.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...
