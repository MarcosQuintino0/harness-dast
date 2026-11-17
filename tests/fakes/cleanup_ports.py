"""Falsos em memória das portas da limpeza, com o comportamento de uma transação de verdade."""

from collections.abc import Mapping
from datetime import datetime

from harness_dast.application.cleanup_ports import CleanupConnection, CleanupSession
from harness_dast.domain.cleanup_binds import BindValue
from harness_dast.domain.cleanup_confirmation import ConfirmationRecord
from harness_dast.domain.cleanup_gate import CleanupStatement
from harness_dast.domain.cleanup_plan import CleanupAuditLine, CleanupPlan, CleanupRecord
from harness_dast.domain.errors import CleanupError
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.run import RunLimits


class FakeDatabase:
    """Banco falso: linhas por tabela, confirmadas ou pendentes na transação.

    `matches[indice_do_comando]` diz quantas linhas o comando apagaria (o falso não interpreta
    o SQL: quem interpreta é o teste de integração contra o Oracle real).
    """

    def __init__(self, tables: Mapping[str, int], matches: Mapping[int, int]) -> None:
        self.committed: dict[str, int] = dict(tables)
        self.matches = dict(matches)
        self.fail_open = False
        self.fail_at: int | None = None
        self.fail_commit = False
        self.fail_rollback = False
        self.pending: dict[str, int] = {}
        self.opened: list[CleanupConnection] = []
        self.executed: list[tuple[int, dict[str, BindValue]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0


class FakeSession:
    """Uma transação sobre `FakeDatabase`: nada vale até o `commit`."""

    def __init__(self, database: FakeDatabase) -> None:
        self._db = database

    def execute(self, statement: CleanupStatement, binds: Mapping[str, BindValue]) -> int:
        self._db.executed.append((statement.index, dict(binds)))
        if self._db.fail_at == statement.index:
            raise CleanupError("Erro do banco ao executar o comando (ORA-02292).")
        rows = self._db.matches.get(statement.index, 0)
        self._db.pending[statement.table] = self._db.pending.get(statement.table, 0) + rows
        return rows

    def commit(self) -> None:
        if self._db.fail_commit:
            raise CleanupError("Erro do banco ao confirmar a transação (ORA-03113).")
        for table, rows in self._db.pending.items():
            self._db.committed[table] = self._db.committed.get(table, 0) - rows
        self._db.pending = {}
        self._db.commits += 1

    def rollback(self) -> None:
        if self._db.fail_rollback:
            raise CleanupError("Erro do banco ao desfazer a transação (ORA-03113).")
        self._db.pending = {}
        self._db.rollbacks += 1

    def close(self) -> None:
        self._db.closed += 1
        self._db.pending = {}


class FakeExecutor:
    """Implementa `CleanupExecutor` sobre um `FakeDatabase`."""

    def __init__(self, database: FakeDatabase) -> None:
        self.database = database

    def open(self, connection: CleanupConnection) -> CleanupSession:
        self.database.opened.append(connection)
        if self.database.fail_open:
            raise CleanupError("Erro do banco ao conectar (DPY-6005).")
        return FakeSession(self.database)


class StaticScripts:
    """Implementa `CleanupScripts` com os bytes dados."""

    def __init__(self, content: str | bytes) -> None:
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.reads = 0

    def read(self, product: str, profile: object) -> bytes:
        self.reads += 1
        return self.content


class InMemoryCleanupRuns:
    """Implementa `CleanupRuns` em memória, com o gasto atômico do token."""

    def __init__(self, manifest: RunManifest | None) -> None:
        self.manifest = manifest
        self.records: list[CleanupRecord] = []
        self.audit: list[CleanupAuditLine] = []
        self.confirmation: ConfirmationRecord | None = None

    def read_manifest(self, run_id: str) -> RunManifest | None:
        if self.manifest is not None and self.manifest.run_id == run_id:
            return self.manifest
        return None

    def write_record(self, run_id: str, record: CleanupRecord) -> None:
        self.records.append(record)

    def append_audit(self, run_id: str, line: CleanupAuditLine) -> None:
        self.audit.append(line)

    def save_confirmation(self, run_id: str, record: ConfirmationRecord) -> None:
        self.confirmation = record

    def load_confirmation(self, run_id: str) -> ConfirmationRecord | None:
        return self.confirmation

    def consume_confirmation(self, run_id: str) -> bool:
        if self.confirmation is None:
            return False
        self.confirmation = None
        return True

    def serialized(self) -> str:
        """Tudo que seria gravado em disco, como texto (para procurar vazamentos)."""
        parts = [r.model_dump_json() for r in self.records]
        parts += [a.model_dump_json() for a in self.audit]
        if self.confirmation is not None:
            parts.append(self.confirmation.model_dump_json())
        return "\n".join(parts)


class SequenceTokens:
    """Implementa `TokenSource` com tokens previsíveis: `tok-1`, `tok-2`..."""

    def __init__(self) -> None:
        self.issued: list[str] = []

    def new_token(self) -> str:
        token = f"tok-{len(self.issued) + 1}"
        self.issued.append(token)
        return token


class ScriptedPrompt:
    """Implementa `OperatorPrompt`: responde sempre `answer` e guarda os planos vistos."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.plans: list[CleanupPlan] = []

    def confirm(self, plan: CleanupPlan) -> bool:
        self.plans.append(plan)
        return self.answer


def finished_manifest(
    run_id: str, product: str, started_at: datetime, *, finished_at: datetime | None
) -> RunManifest:
    """Manifesto de uma execução (terminada se `finished_at` for dado)."""
    return RunManifest(
        run_id=run_id,
        command="probe",
        product=product,
        harness_version="0.0-teste",
        hashes=ArtifactHashes(),
        limits=RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2),
        seed=1,
        accounts=("user_a",),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat() if finished_at else None,
        status="completed" if finished_at else "running",
    )
