"""Caso de uso `cleanup`: apaga, em uma transação confirmada por uma pessoa, o lixo de uma execução.

É a única parte do sistema que apaga dados de propósito; por isso é lenta, explícita e humana.
A ordem é fixa e tudo que pode ser recusado é recusado ANTES de abrir qualquer conexão:

1. a execução existe, é do produto e já terminou; a autorização do perfil ainda vale (a janela
   NÃO é exigida: a limpeza não envia nada ao alvo e deixar lixo até a próxima janela é pior);
2. o perfil tem tudo que a limpeza exige (usuário, senha, `allowed_tables`, `max_rows`);
3. o script passa no portão (`domain.cleanup_gate`) e as variáveis do contrato são resolvidas;
4. a forma de confirmar existe: `--dry-run`, terminal interativo (a pessoa digita o produto) ou,
   só por este caso de uso (a CLI não o expõe, ADR 0025), um token válido (gasto aqui);
5. só então conecta, abre UMA transação, roda os comandos, confere os tetos e decide:
   `--dry-run` sempre desfaz; sem confirmação da pessoa, desfaz; qualquer erro desfaz.

Nenhum valor de ligação nem credencial entra em relatório, auditoria, log ou mensagem de erro.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import Field, SecretStr, ValidationError

from harness_dast.application.ports import (
    CleanupConnection,
    CleanupExecutor,
    CleanupRuns,
    CleanupScripts,
    CleanupSession,
    Clock,
    OperatorPrompt,
    ProfileRepository,
    SecretProvider,
    SecretVault,
    TokenSource,
)
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.cleanup_binds import (
    BindValue,
    build_binds,
    parse_run_start,
    select_binds,
)
from harness_dast.domain.cleanup_confirmation import issue_record, verify_token
from harness_dast.domain.cleanup_gate import CleanupPolicy, CleanupScript, parse_cleanup_script
from harness_dast.domain.cleanup_plan import (
    CleanupAuditLine,
    CleanupPlan,
    CleanupRecord,
    CleanupStatus,
    ConfirmationMethod,
    StatementResult,
    ensure_within_ceiling,
    run_is_finished,
)
from harness_dast.domain.errors import CleanupError, ConfigError
from harness_dast.domain.probe_result import RunManifest
from harness_dast.domain.profile import CleanupConfig, ProductProfile
from harness_dast.domain.run import RunId
from harness_dast.domain.secret_ref import SecretRef

CONNECT_TIMEOUT_SECONDS = 15
CALL_TIMEOUT_SECONDS = 120
_UNEXPECTED = "A limpeza parou por um erro inesperado (a transação foi desfeita)."
_PROFILE_HINT = (
    "Complete o bloco cleanup do target.yml (veja docs/operations/cleanup.md): user e password "
    "(secret_ref), allowed_tables e max_rows."
)


class StatementFailed(CleanupError):
    """Um comando do script falhou no banco (a transação foi desfeita).

    Attributes:
        index: Posição do comando no script.
        table: Tabela do comando.
    """

    def __init__(self, index: int, table: str, cause: CleanupError) -> None:
        """Cria o erro citando o índice e a tabela, nunca os valores de ligação."""
        super().__init__(
            f"Falha no comando {index} do script (tabela {table}): {cause.message}",
            hint="Nada foi gravado (ROLLBACK). Corrija o script ou o banco e rode de novo.",
        )
        self.index = index
        self.table = table


@dataclass(frozen=True)
class CleanupRequest:
    """Pedido de limpeza.

    Attributes:
        product: Produto.
        run_id: Execução a limpar.
        dry_run: Executa e SEMPRE desfaz; emite o token de confirmação.
        confirm_token: Token de um `--dry-run` anterior. A CLI nunca o preenche (ADR 0025): só
            quem usa o caso de uso em processo o tem.
        interactive: Se há uma pessoa em um terminal para confirmar digitando o produto.
    """

    product: str
    run_id: str
    dry_run: bool
    confirm_token: str | None
    interactive: bool


class CleanupReport(CleanupRecord):
    """`CleanupRecord` mais o token emitido pelo `--dry-run`.

    Attributes:
        confirmation_token: Token em claro. EXCLUÍDO de toda serialização (`model_dump`, JSON,
            `cleanup.json`): a CLI o escreve só no stderr da pessoa que operou.
    """

    confirmation_token: str | None = Field(default=None, exclude=True, repr=False)


@dataclass(frozen=True)
class _Ready:
    """O bloco `cleanup` do perfil com os campos obrigatórios já garantidos."""

    config: CleanupConfig
    user: SecretRef
    password: SecretRef
    max_rows: int


@dataclass
class _Job:
    request: CleanupRequest
    max_rows: int
    script: CleanupScript
    binds: dict[str, BindValue]
    connection: CleanupConnection
    method: ConfirmationMethod
    token_ceiling: int | None


@dataclass
class _Attempt:
    results: list[StatementResult] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    token: str | None = None
    token_expires_at: str | None = None


class Cleanup:
    """Executa a limpeza de uma execução (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        scripts: CleanupScripts,
        runs: CleanupRuns,
        secrets: SecretProvider,
        vault: SecretVault,
        executor: CleanupExecutor,
        prompt: OperatorPrompt,
        tokens: TokenSource,
        clock: Clock,
    ) -> None:
        """Cria o caso de uso com as portas de que precisa."""
        self._profiles = profiles
        self._scripts = scripts
        self._runs = runs
        self._secrets = secrets
        self._vault = vault
        self._executor = executor
        self._prompt = prompt
        self._tokens = tokens
        self._clock = clock

    def execute(self, request: CleanupRequest) -> CleanupReport:
        """Roda a limpeza.

        Returns:
            O relatório. `status` é `dry_run`, `committed` ou `declined`.

        Raises:
            ConfigError: Execução, perfil, script, segredo ou confirmação inválidos; nada foi
                conectado.
            ScopeViolation: Autorização vencida.
            CleanupError: Falha no banco, teto de linhas excedido ou erro ao confirmar. A
                transação foi desfeita (exceto se o erro for ao confirmar: confira o banco).
        """
        job = self._prepare(request)
        started = self._clock.now()
        self._audit(job, "started", started)
        attempt = _Attempt()
        session: CleanupSession | None = None
        status: CleanupStatus | None = None
        handled = False
        try:
            session = self._executor.open(job.connection)
            status = self._work(session, job, attempt)
        except CleanupError as error:
            handled = True
            attempt.rolled_back = self._rollback(session)
            self._finish(job, attempt, "failed", started, error)
            raise
        finally:
            if status is None and not handled:
                # Exceção que não é do harness (driver, disco): a trilha não pode ficar com uma
                # tentativa "started" sem "finished". Desfaz, registra, e a exceção segue.
                attempt.rolled_back = self._rollback(session)
                self._finish(job, attempt, "failed", started, CleanupError(_UNEXPECTED))
            if session is not None:
                session.close()
        return self._finish(job, attempt, status, started, None)

    # ------------------------------------------------------------ preparação

    def _prepare(self, request: CleanupRequest) -> _Job:
        try:
            run_id = RunId(value=request.run_id).value
        except ValidationError:
            raise ConfigError(
                "Identificador de execução inválido.", hint="Use o run_id devolvido pelo probe."
            ) from None
        profile = self._profiles.load(request.product)
        ready = self._require_cleanup(profile)
        manifest = self._check_run(request.product, run_id, profile)
        refs = self._username_refs(profile)
        policy = CleanupPolicy(
            allowed_tables=frozenset(ready.config.allowed_tables), account_count=len(refs)
        )
        script = parse_cleanup_script(self._scripts.read(request.product, profile), policy)
        usernames = [
            self._secret(ref, f"auth.accounts[{n}].username") for n, ref in enumerate(refs)
        ]
        binds = build_binds(
            run_id=run_id, started_at=parse_run_start(manifest.started_at), usernames=usernames
        )
        method, ceiling = self._confirmation(request, run_id, script)
        return _Job(
            request, ready.max_rows, script, dict(binds), self._connection(ready), method, ceiling
        )

    @staticmethod
    def _require_cleanup(profile: ProductProfile) -> _Ready:
        cleanup = profile.cleanup
        if cleanup is None:
            raise ConfigError(
                "O perfil não tem o bloco cleanup.",
                hint="Adicione cleanup ao target.yml (veja docs/reference/target-yml.md).",
            )
        missing = cleanup.missing_for_run()
        if cleanup.user is None or cleanup.password is None or cleanup.max_rows is None or missing:
            raise ConfigError(
                f"A limpeza exige campos que o perfil não tem: {', '.join(missing)}.",
                hint=_PROFILE_HINT,
            )
        return _Ready(cleanup, cleanup.user, cleanup.password, cleanup.max_rows)

    def _check_run(self, product: str, run_id: str, profile: ProductProfile) -> RunManifest:
        manifest = self._runs.read_manifest(run_id)
        if manifest is None:
            raise ConfigError(
                "A execução não foi encontrada.", hint="Confira o run_id e HDAST_RUNS_DIR."
            )
        if manifest.product != product or manifest.run_id != run_id:
            raise ConfigError(
                "A execução pertence a outro produto.", hint="Use o run_id deste produto."
            )
        now = self._clock.now()
        finished = run_is_finished(
            finished_at=manifest.finished_at,
            started_at=parse_run_start(manifest.started_at),
            max_duration_minutes=manifest.limits.max_duration_minutes,
            now=now,
        )
        if not finished:
            raise ConfigError(
                "A execução ainda está em andamento.",
                hint="Espere o probe terminar; não limpe dados enquanto a varredura roda.",
            )
        profile.scope.authorization.ensure_valid(now)
        return manifest

    @staticmethod
    def _username_refs(profile: ProductProfile) -> tuple[SecretRef, ...]:
        if isinstance(profile.auth, PasswordLoginAuth):
            return tuple(account.username for account in profile.auth.accounts)
        return ()

    def _secret(self, ref: SecretRef, field_name: str) -> str:
        value = self._secrets.resolve(ref)
        if value is None:
            raise ConfigError(
                f"O segredo de {field_name} não está definido ou está vazio.",
                hint="Defina a variável de ambiente indicada no target.yml e tente de novo.",
            )
        self._vault.register(value)
        return value

    def _connection(self, ready: _Ready) -> CleanupConnection:
        return CleanupConnection(
            dsn=self._secret(ready.config.connection, "cleanup.connection"),
            user=self._secret(ready.user, "cleanup.user"),
            password=SecretStr(self._secret(ready.password, "cleanup.password")),
            db_schema=ready.config.db_schema,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            call_timeout_seconds=CALL_TIMEOUT_SECONDS,
        )

    def _confirmation(
        self, request: CleanupRequest, run_id: str, script: CleanupScript
    ) -> tuple[ConfirmationMethod, int | None]:
        if request.dry_run:
            if request.confirm_token is not None:
                raise ConfigError("--dry-run e --confirm não combinam.", hint="Use um por vez.")
            return "none", None
        if request.confirm_token is not None:
            record = verify_token(
                self._runs.load_confirmation(run_id),
                request.confirm_token,
                product=request.product,
                run_id=run_id,
                script_sha256=script.sha256,
                now=self._clock.now(),
            )
            if not self._runs.consume_confirmation(run_id):
                raise ConfigError("O token de confirmação já foi usado.", hint="Rode --dry-run.")
            return "token", record.rows_ceiling
        if request.interactive:
            return "interactive", None
        raise ConfigError(
            "Sem terminal interativo: a limpeza de verdade não será executada.",
            hint=(
                "Só uma pessoa, em um terminal interativo, confirma digitando o nome do produto. "
                "Esta tarefa não é de agente: peça ao dono do produto."
            ),
        )

    # -------------------------------------------------------------- execução

    def _work(self, session: CleanupSession, job: _Job, attempt: _Attempt) -> CleanupStatus:
        for statement in job.script.statements:
            try:
                rows = session.execute(statement, select_binds(job.binds, statement.binds))
            except CleanupError as error:
                raise StatementFailed(statement.index, statement.table, error) from None
            attempt.results.append(
                StatementResult(index=statement.index, table=statement.table, rows=rows)
            )
        plan = self._plan(job, attempt)
        ensure_within_ceiling(plan.total_rows, job.max_rows, source="cleanup.max_rows")
        if job.token_ceiling is not None:
            ensure_within_ceiling(
                plan.total_rows, job.token_ceiling, source="o total visto no --dry-run"
            )
        if job.request.dry_run:
            return self._dry_run(session, job, attempt, plan)
        if job.method == "token" or self._prompt.confirm(plan):
            session.commit()
            attempt.committed = True
            return "committed"
        session.rollback()
        attempt.rolled_back = True
        return "declined"

    def _dry_run(
        self, session: CleanupSession, job: _Job, attempt: _Attempt, plan: CleanupPlan
    ) -> CleanupStatus:
        session.rollback()
        attempt.rolled_back = True
        token = self._tokens.new_token()
        record = issue_record(
            token=token,
            product=plan.product,
            run_id=plan.run_id,
            script_sha256=plan.script_sha256,
            rows_ceiling=plan.total_rows,
            now=self._clock.now(),
        )
        self._runs.save_confirmation(plan.run_id, record)
        attempt.token = token
        attempt.token_expires_at = record.expires_at
        return "dry_run"

    @staticmethod
    def _plan(job: _Job, attempt: _Attempt) -> CleanupPlan:
        return CleanupPlan(
            product=job.request.product,
            run_id=job.request.run_id,
            script_sha256=job.script.sha256,
            results=tuple(attempt.results),
            max_rows=job.max_rows,
        )

    @staticmethod
    def _rollback(session: CleanupSession | None) -> bool:
        if session is None:
            return True  # nunca houve transação
        try:
            session.rollback()
        except CleanupError:
            return False
        return True

    # ------------------------------------------------------- relatório e trilha

    def _audit(
        self,
        job: _Job,
        event: Literal["started", "finished"],
        at: datetime,
        status: CleanupStatus | None = None,
        total: int | None = None,
    ) -> None:
        line = CleanupAuditLine.model_validate(
            {
                "event": event,
                "at": at.isoformat(),
                "product": job.request.product,
                "run_id": job.request.run_id,
                "script_sha256": job.script.sha256,
                "mode": "dry_run" if job.request.dry_run else "execute",
                "confirmation_method": job.method,
                "status": status,
                "total_rows": total,
            }
        )
        self._runs.append_audit(job.request.run_id, line)

    def _finish(
        self,
        job: _Job,
        attempt: _Attempt,
        status: CleanupStatus,
        started: datetime,
        error: CleanupError | None,
    ) -> CleanupReport:
        finished = self._clock.now()
        total = sum(result.rows for result in attempt.results)
        failed = error if isinstance(error, StatementFailed) else None
        report = CleanupReport(
            run_id=job.request.run_id,
            product=job.request.product,
            status=status,
            script_sha256=job.script.sha256,
            statement_count=len(job.script.statements),
            tables=job.script.tables,
            statements=tuple(attempt.results),
            total_rows=total,
            max_rows=job.max_rows,
            confirmation_method=job.method,
            committed=attempt.committed,
            rolled_back=attempt.rolled_back,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_ms=int((finished - started).total_seconds() * 1000),
            failed_statement=failed.index if failed else None,
            failed_table=failed.table if failed else None,
            error_code=error.code if error else None,
            token_expires_at=attempt.token_expires_at,
            confirmation_token=attempt.token,
        )
        self._runs.write_record(job.request.run_id, report)
        self._audit(job, "finished", finished, status, total)
        return report
