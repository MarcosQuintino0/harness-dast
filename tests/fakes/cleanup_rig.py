"""Montagem do caso de uso `Cleanup` sobre falsos, com um produto, uma execução e um script."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from harness_dast.application.cleanup import Cleanup, CleanupReport, CleanupRequest
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.cleanup_ports import (
    FakeDatabase,
    FakeExecutor,
    InMemoryCleanupRuns,
    ScriptedPrompt,
    SequenceTokens,
    StaticScripts,
    finished_manifest,
)
from tests.fakes.probe_ports import DictSecretProvider
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.runtime import ManualClock

RUN_ID = "2026-11-10T10-00-00Z-demo-7f3a"
STARTED = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
FINISHED = datetime(2026, 11, 10, 10, 30, tzinfo=UTC)
SCRIPT = (
    "-- limpeza de teste\n"
    "DELETE FROM ITEM WHERE RUN_ID = :run_id;\n"
    "DELETE FROM PEDIDO WHERE CREATED_AT >= :run_start AND CREATED_BY = :account_1;\n"
)
SECRETS = {
    "ACME_USER_A_LOGIN": "login-conta-a-SEGREDO",
    "ACME_USER_A_SENHA": "senha-conta-a-SEGREDO",
    "ACME_ORACLE_DSN": "host-oracle-SEGREDO:1521/FREEPDB1",
    "ACME_ORACLE_USER": "usuario-limpeza-SEGREDO",
    "ACME_ORACLE_PASSWORD": "senha-banco-SEGREDO",
}


def cleanup_profile(
    *, valid_until: str | None = None, window: str | None = None, **cleanup_changes: Any
) -> ProductProfile:
    """Perfil `demo` com o bloco `cleanup` completo; `cleanup_changes` sobrescreve campos.

    Args:
        valid_until: Sobrescreve a validade da autorização (`AAAA-MM-DD`).
        window: Sobrescreve a janela de execução (forma compacta).
        **cleanup_changes: Campos do bloco `cleanup`.
    """
    data = valid_profile_data("demo", with_cleanup=True)
    if valid_until is not None:
        data["scope"]["authorization"]["valid_until"] = valid_until
    if window is not None:
        data["scope"]["windows"] = [window]
    data["cleanup"] = {
        "type": "oracle_sql",
        "script": "./cleanup/cleanup.sql",
        "connection": {"secret_ref": "env:ACME_ORACLE_DSN"},
        "user": {"secret_ref": "env:ACME_ORACLE_USER"},
        "password": {"secret_ref": "env:ACME_ORACLE_PASSWORD"},
        "allowed_tables": ["PEDIDO", "ITEM"],
        "max_rows": 100,
        "requires_confirmation": True,
        **cleanup_changes,
    }
    return ProductProfile.from_data(data)


@dataclass
class CleanupRig:
    """Todos os falsos e o caso de uso; os testes mexem nos falsos antes de `run`."""

    profile: ProductProfile = field(default_factory=cleanup_profile)
    script: str = SCRIPT
    matches: dict[int, int] = field(default_factory=lambda: {1: 3, 2: 2})
    finished_at: datetime | None = FINISHED
    secrets: dict[str, str] = field(default_factory=lambda: dict(SECRETS))
    prompt_answer: bool = True

    def __post_init__(self) -> None:
        self.database = FakeDatabase({"PEDIDO": 10, "ITEM": 20}, self.matches)
        self.executor = FakeExecutor(self.database)
        self.scripts = StaticScripts(self.script)
        self.runs = InMemoryCleanupRuns(
            finished_manifest(RUN_ID, "demo", STARTED, finished_at=self.finished_at)
        )
        self.tokens = SequenceTokens()
        self.prompt = ScriptedPrompt(self.prompt_answer)
        self.clock = ManualClock(datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
        self.vault = SecretRegistry()
        repository = InMemoryProfileRepository()
        repository.add(self.profile)
        self.use_case = Cleanup(
            profiles=repository,
            scripts=self.scripts,
            runs=self.runs,
            secrets=DictSecretProvider(self.secrets),
            vault=self.vault,
            executor=self.executor,
            prompt=self.prompt,
            tokens=self.tokens,
            clock=self.clock,
        )

    def run(
        self,
        *,
        dry_run: bool = False,
        confirm: str | None = None,
        interactive: bool = False,
        run_id: str = RUN_ID,
    ) -> CleanupReport:
        """Executa o caso de uso com os argumentos dados."""
        return self.use_case.execute(
            CleanupRequest(
                product="demo",
                run_id=run_id,
                dry_run=dry_run,
                confirm_token=confirm,
                interactive=interactive,
            )
        )
