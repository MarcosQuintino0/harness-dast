"""Porta do teste de autorização: os arquivos da execução que ele lê e grava.

Fica aqui, e não em `ports.py`, pelo mesmo motivo de `scan_ports.py`: `ports.py` é compartilhado
e a regra é a mesma (porta declarada por quem a consome, sem regra de negócio). O adaptador é
`adapters/reporting/run_files.py`.
"""

from typing import Protocol

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult


class AuthzArtifacts(Protocol):
    """Arquivos de uma execução que o `authz` lê (do `probe`) e grava (`authz.json`)."""

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

    def write_authz(self, run_id: str, result: AuthzResult) -> None:
        """Grava `authz.json` de forma atômica.

        Raises:
            ConfigError: Falha de escrita.
        """
        ...


class AuthzDraftWriter(Protocol):
    """Grava o rascunho da tabela "quem pode o quê" na pasta do produto (ADR 0041)."""

    def write_draft(self, product: str, text: str) -> str:
        """Grava `authz-matrix.draft.yml` SEM sobrescrever nada.

        Returns:
            O caminho do arquivo gravado.

        Raises:
            ConfigError: Produto inexistente, arquivo já existente (nunca é sobrescrito) ou
                falha de escrita.
        """
        ...
