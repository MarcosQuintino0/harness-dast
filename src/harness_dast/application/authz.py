"""Caso de uso `authz`: teste de autorização entre contas sobre o que o `probe` alcançou (ADR 0027).

Fluxo: lê `probe.json` e `exchanges.json` da execução, confere perfil, janela e autorização
agora, planeja no domínio (puro) o que repetir e com qual conta, e, sem `--dry-run`, envia os
pedidos pelo MESMO caminho do `probe` (`OperationDispatcher` sobre `GuardedSender`). Grava
`authz.json`. Determinístico: não usa o ZAP, não inventa caminho, não troca método e não
adivinha identificador. Achado é dado para o agente (não vira erro do comando); só paradas no
meio (janela, prazo, ZAP, alvo sem resposta) viram código de saída, como no `probe`.

Escrita só com a carta (ADR 0038): sem `authz.allow_writes` a atribuição em massa e os métodos de
escrita de `vertical_methods` ficam fora do plano e aparecem em `not_tested` com o motivo; pedir
`--check mass_assignment` não liga a escrita (flags só reduzem).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.authz_ports import AuthzArtifacts
from harness_dast.application.authz_runner import (
    AuthzOutcome,
    AuthzPlans,
    AuthzRunner,
    AuthzSettings,
)
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.ports import (
    Clock,
    KillSwitch,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    SpecLoader,
    TargetClient,
)
from harness_dast.application.run_support import AuditTrail, GuardedSender, RateLimiter, RunGate
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_anonymous import plan_access
from harness_dast.domain.authz_config import CHECK_ORDER, AuthzCheck
from harness_dast.domain.authz_matrix_plan import MatrixPlan, plan_access_matrix
from harness_dast.domain.authz_plan import (
    Planned,
    ReplayTask,
    plan_excessive,
    plan_horizontal,
    plan_vertical,
)
from harness_dast.domain.authz_plan_mass import (
    MassTask,
    count_candidates,
    describe_plan,
    plan_mass_assignment,
)
from harness_dast.domain.authz_plan_write import WriteTask, plan_horizontal_write
from harness_dast.domain.authz_result import AuthzNotTested, AuthzResult, CheckSummary
from harness_dast.domain.authz_writes import (
    EXCHANGES_UNAVAILABLE,
    NO_EXCHANGES,
    horizontal_write_blocked_note,
    mass_blocked_note,
    nothing_to_replay_notes,
    vertical_dropped_note,
)
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run_ref import require_run_id


@dataclass(frozen=True)
class AuthzRequest:
    """Pedido de um `authz`.

    Attributes:
        product: Nome do produto.
        run_id: Execução do `probe` (com `exchanges.json`).
        checks: Verificações pedidas; vazio roda todas as que o perfil não desligou. Só
            reduz: nunca liga o que o perfil desligou.
        dry_run: Só planeja (o que seria repetido e o que fica sem teste); nada é enviado nem
            gravado.
        deadline: Prazo absoluto herdado do `run` encadeado; só reduz o prazo do perfil.
        tolerate_missing_exchanges: Usado pelo estágio do `run`: se `exchanges.json` não puder
            ser lido, o estágio não derruba a execução; cada verificação vai para `not_tested`
            com o motivo. O comando `hdast authz` solto continua recusando (erro de configuração).
    """

    product: str
    run_id: str
    checks: tuple[AuthzCheck, ...] = ()
    dry_run: bool = False
    deadline: datetime | None = None
    tolerate_missing_exchanges: bool = False


class _ContinuingTrail(AuditTrail):
    """Trilha de auditoria que continua a numeração do `audit.jsonl` da execução."""

    def __init__(self, store: RunStore, run_id: str, clock: Clock, last_seq: int) -> None:
        super().__init__(store, run_id, clock)
        self._seq = last_seq


class Authz:
    """Orquestra o `authz` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        store: RunStore,
        artifacts: AuthzArtifacts,
        clock: Clock,
        sleeper: Sleeper,
        token_cache: TokenCache | None = None,
        login_budget: LoginBudget | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        """Cria o caso de uso com todas as portas de que precisa.

        `token_cache`, `login_budget` e `kill_switch` são compartilhados com as outras etapas
        quando o `run` encadeia tudo num processo só (cada conta faz login uma vez).
        """
        self._profiles = profiles
        self._specs = specs
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._store = store
        self._artifacts = artifacts
        self._clock = clock
        self._sleeper = sleeper
        self._token_cache = token_cache
        self._login_budget = login_budget
        self._kill_switch = kill_switch

    def execute(self, request: AuthzRequest) -> AuthzResult:
        """Executa o `authz`.

        Args:
            request: Pedido.

        Returns:
            O resultado completo. Mesmo com parada antecipada o resultado parcial é devolvido e
            gravado em `authz.json` (exceto em `--dry-run`).

        Raises:
            ConfigError: Perfil, execução ou argumentos inválidos; `probe` sem envio ou sem
                `exchanges.json`.
            ScopeViolation: Autorização vencida ou janela fechada na partida.
        """
        started = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(started)
        run_id = require_run_id(request.run_id)
        probe = self._artifacts.read_probe(run_id)
        if probe.product != profile.product:
            raise ConfigError(
                "A execução informada é de outro produto.",
                hint="Use o run_id do probe deste produto.",
            )
        if probe.dry_run:
            raise ConfigError(
                "O probe desta execução foi uma simulação (--dry-run): não há pedidos a repetir.",
                hint="Rode o probe sem --dry-run e use o run_id dele.",
            )
        exchanges, unavailable = self._read_exchanges(request, run_id, profile)
        spec = self._specs.load(request.product, profile)
        operation_ids = [op.operation_id for op in spec.operations]
        profile.authz.ensure_operations_exist(operation_ids)
        profile.authz.ensure_matrix_valid(operation_ids, [a.role for a in profile.auth.accounts])
        checks = profile.authz.enabled_checks(request.checks)
        plans = _plan(profile, exchanges, checks, spec.operations, unavailable)
        if request.dry_run:
            outcome = _dry_outcome(checks, plans)
        else:
            outcome = self._run(profile, request, spec.operations, plans, checks, started, run_id)
        result = AuthzResult(
            run_id=run_id,
            product=profile.product,
            dry_run=request.dry_run,
            status=outcome.status,
            stop_message=outcome.stop_message,
            started_at=started.isoformat(),
            finished_at=self._clock.now().isoformat(),
            requests_sent=outcome.requests_sent,
            created_resources=outcome.created_resources,
            accounts=outcome.accounts,
            access_matrix=outcome.access_matrix,
            checks=_all_checks(outcome.checks, profile),
            findings=outcome.findings,
            not_tested=outcome.not_tested,
        )
        if not request.dry_run:
            self._artifacts.write_authz(run_id, result)
        return result

    def _read_exchanges(
        self, request: AuthzRequest, run_id: str, profile: ProductProfile
    ) -> tuple[tuple[ExchangeRecord, ...], str | None]:
        """Pedidos do `probe` e, se indisponíveis no modo tolerante, o porquê.

        Raises:
            ConfigError: `exchanges.json` ausente ou inválido fora do modo tolerante, ou de outro
                produto.
        """
        try:
            log = self._artifacts.read_exchanges(run_id)
        except ConfigError as error:
            if not request.tolerate_missing_exchanges:
                raise
            return (), error.message
        if log.product != profile.product:
            raise ConfigError(
                "A execução informada é de outro produto.",
                hint="Use o run_id do probe deste produto.",
            )
        return log.exchanges, None

    def _run(
        self,
        profile: ProductProfile,
        request: AuthzRequest,
        operations: tuple[Operation, ...],
        plans: AuthzPlans,
        checks: tuple[AuthzCheck, ...],
        started: datetime,
        run_id: str,
    ) -> AuthzOutcome:
        last_seq = max((entry.seq for entry in self._artifacts.read_audit(run_id)), default=0)
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._client,
            gate=RunGate(
                profile, self._clock, started, self._kill_switch, deadline=request.deadline
            ),
            limiter=RateLimiter(profile.limits.requests_per_second, self._clock, self._sleeper),
            trail=_ContinuingTrail(self._store, run_id, self._clock, last_seq),
            clock=self._clock,
        )
        budget = self._login_budget or LoginBudget(profile.login_limit, self._clock, self._sleeper)
        dispatcher = OperationDispatcher(
            sender,
            self._sleeper,
            profile.auth.csrf,
            login_budget=budget,
            login_path=profile.login_path,
            token_expired=profile.token_expired_signal,
            error_codes=profile.probe.error_codes,
        )
        pool = SessionPool(lambda alias: self._session(profile, alias, dispatcher))
        runner = AuthzRunner(
            AuthzSettings(
                product=profile.product,
                base_url=profile.environment.base_url,
                config=profile.authz,
                roles={a.alias: a.role for a in profile.auth.accounts},
                operations={op.operation_id: op for op in operations},
                dispatcher=dispatcher,
                sessions=pool,
                vault=self._vault,
            )
        )
        return runner.run(checks, plans)

    def _session(
        self, profile: ProductProfile, alias: str, dispatcher: OperationDispatcher
    ) -> AccountSession:
        return AccountSession(
            account=profile.select_account(alias),
            auth=profile.auth,
            base_url=profile.environment.base_url,
            secrets=self._secrets,
            vault=self._vault,
            client=self._client,
            dispatcher=dispatcher,
            token_cache=self._token_cache,
        )


def _plan(
    profile: ProductProfile,
    exchanges: tuple[ExchangeRecord, ...],
    checks: tuple[AuthzCheck, ...],
    operations: tuple[Operation, ...],
    unavailable: str | None = None,
) -> AuthzPlans:
    config = profile.authz
    roles = {account.alias: account.role for account in profile.auth.accounts}
    public = frozenset(config.public_operations)
    empty: Planned[ExchangeRecord] = Planned((), ())

    def assigned(item: ExchangeRecord) -> str | None:
        return profile.auth.explicit_account(item.operation_id, item.method, item.path)

    matrix = MatrixPlan()
    if "access_matrix" in checks and config.access_matrix:
        matrix = plan_access_matrix(
            config.access_matrix,
            exchanges,
            roles,
            config.role_order,
            {op.operation_id: op for op in operations},
            allow_writes=config.allow_writes,
        )
    vertical: Planned[ReplayTask] = Planned((), ())
    if "vertical" in checks:
        vertical = plan_vertical(
            exchanges,
            roles,
            config.role_order,
            assigned,
            config.effective_vertical_methods(),
            public,
            frozenset(rule.operation for rule in config.access_matrix)
            if "access_matrix" in checks
            else frozenset(),
        )
        dropped = config.dropped_write_methods()
        if dropped:
            vertical = _noted(vertical, vertical_dropped_note(dropped))
    mass: Planned[MassTask] = Planned((), ())
    if "mass_assignment" in checks:
        mass = (
            plan_mass_assignment(
                exchanges, public, config, operations, profile.infrastructure_paths
            )
            if config.allow_writes
            else Planned((), (mass_blocked_note(),))
        )
    write: Planned[WriteTask] = Planned((), ())
    if "horizontal_write" in checks:
        write = (
            plan_horizontal_write(exchanges, roles, public, operations, config.id_parameters)
            if config.allow_writes
            else Planned((), (horizontal_write_blocked_note(),))
        )
    plans = AuthzPlans(
        anonymous=_access("anonymous_access", profile, exchanges, operations, checks),
        tampered=_access("tampered_token", profile, exchanges, operations, checks),
        horizontal=plan_horizontal(exchanges, roles, public, operations, config.id_parameters)
        if "horizontal" in checks
        else Planned((), ()),
        excessive=plan_excessive(exchanges) if "excessive_data" in checks else empty,
        vertical=vertical,
        matrix=matrix,
        mass=mass,
        horizontal_write=write,
    )
    return plans if exchanges else _nothing_to_replay(plans, checks, unavailable)


def _access(
    check: Literal["anonymous_access", "tampered_token"],
    profile: ProductProfile,
    exchanges: tuple[ExchangeRecord, ...],
    operations: tuple[Operation, ...],
    checks: tuple[AuthzCheck, ...],
) -> Planned[ExchangeRecord]:
    """Plano de uma verificação de acesso (vazio se ela não foi pedida)."""
    if check not in checks:
        return Planned((), ())
    infrastructure = profile.infrastructure_paths
    return plan_access(
        check,
        exchanges,
        {op.operation_id: op for op in operations},
        frozenset(profile.authz.public_operations),
        infrastructure,
    )


def _noted[T](plan: Planned[T], *notes: AuthzNotTested) -> Planned[T]:
    return Planned(plan.tasks, (*plan.not_tested, *notes))


def _nothing_to_replay(
    plans: AuthzPlans, checks: tuple[AuthzCheck, ...], unavailable: str | None
) -> AuthzPlans:
    """Sem pedido do `probe`, cada verificação diz o porquê em vez de sumir."""
    if unavailable is None:
        reason = NO_EXCHANGES
        why = (
            "O probe não registrou nenhum pedido com sucesso (exchanges.json vazio): não há "
            "o que repetir. Faça o probe alcançar operações (fix-reachability) e rode de novo."
        )
    else:
        reason = EXCHANGES_UNAVAILABLE
        why = f"Os pedidos do probe não puderam ser lidos ({unavailable}): nada foi repetido."
    notes = nothing_to_replay_notes(checks, reason=reason, why=why)
    return AuthzPlans(
        horizontal=_noted(plans.horizontal, *_note(notes, "horizontal")),
        excessive=_noted(plans.excessive, *_note(notes, "excessive_data")),
        anonymous=_noted(plans.anonymous, *_note(notes, "anonymous_access")),
        tampered=_noted(plans.tampered, *_note(notes, "tampered_token")),
        vertical=_noted(plans.vertical, *_note(notes, "vertical")),
        matrix=replace(plans.matrix, notes=(*plans.matrix.notes, *_note(notes, "access_matrix"))),
        mass=_noted(plans.mass, *_note(notes, "mass_assignment")),
        horizontal_write=_noted(plans.horizontal_write, *_note(notes, "horizontal_write")),
    )


def _note(notes: dict[AuthzCheck, AuthzNotTested], check: AuthzCheck) -> tuple[AuthzNotTested, ...]:
    return (notes[check],) if check in notes else ()


def _dry_outcome(checks: tuple[AuthzCheck, ...], plans: AuthzPlans) -> AuthzOutcome:
    sizes = {
        "horizontal": plans.horizontal,
        "excessive_data": plans.excessive,
        "anonymous_access": plans.anonymous,
        "tampered_token": plans.tampered,
        "vertical": plans.vertical,
        "access_matrix": plans.matrix.planned,
        "mass_assignment": plans.mass,
        "horizontal_write": plans.horizontal_write,
    }
    summaries = tuple(_dry_summary(check, plans, sizes[check].tasks) for check in checks)
    summaries = tuple(_dry_matrix(item, plans) for item in summaries)
    skipped = tuple(item for check in checks for item in sizes[check].not_tested)
    return AuthzOutcome("completed", None, summaries, (), skipped, 0, ())


def _dry_summary(check: AuthzCheck, plans: AuthzPlans, tasks: Sequence[object]) -> CheckSummary:
    message = "Simulação (--dry-run): nada foi enviado."
    count = len(tasks)
    if check == "mass_assignment":
        count = count_candidates(plans.mass.tasks)
        if plans.mass.tasks:
            message += f" Campos por operação: {describe_plan(plans.mass.tasks)}."
    return CheckSummary(check=check, status="skipped", candidates=count, message=message)


def _dry_matrix(summary: CheckSummary, plans: AuthzPlans) -> CheckSummary:
    """Na simulação, os candidatos da tabela são as células proibidas, não os pedidos a enviar."""
    if summary.check != "access_matrix":
        return summary
    return summary.model_copy(update={"candidates": plans.matrix.candidates})


def _all_checks(ran: tuple[CheckSummary, ...], profile: ProductProfile) -> tuple[CheckSummary, ...]:
    """Uma linha por verificação, na ordem fixa; as não rodadas aparecem como `disabled`."""
    by_name = {summary.check: summary for summary in ran}
    rows: list[CheckSummary] = []
    for check in CHECK_ORDER:
        writes = check in ("mass_assignment", "horizontal_write")
        if writes and check in by_name and not profile.authz.allow_writes:
            blocked = "Não rodou: escrita não autorizada pela carta (authz.allow_writes)."
            rows.append(by_name[check].model_copy(update={"message": blocked}))
        elif check == "access_matrix" and check in by_name and not profile.authz.access_matrix:
            empty = "Perfil sem authz.access_matrix: nada a testar."
            rows.append(by_name[check].model_copy(update={"message": empty}))
        elif check in by_name:
            rows.append(by_name[check])
        else:
            why = (
                "desligada em authz.disabled_checks"
                if check in profile.authz.disabled_checks
                else "não pedida (--check)"
            )
            rows.append(CheckSummary(check=check, status="disabled", message=f"Não rodou: {why}."))
    return tuple(rows)
