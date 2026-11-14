"""Caso de uso `authz`: teste de autorização entre contas sobre o que o `probe` alcançou (ADR 0027).

Fluxo: lê `probe.json` e `exchanges.json` da execução, confere perfil, janela e autorização
agora, planeja no domínio (puro) o que repetir e com qual conta, e, sem `--dry-run`, envia os
pedidos pelo MESMO caminho do `probe` (`OperationDispatcher` sobre `GuardedSender`). Grava
`authz.json`. Determinístico: não usa o ZAP, não inventa caminho, não troca método e não
adivinha identificador. Achado é dado para o agente (não vira erro do comando); só paradas no
meio (janela, prazo, ZAP, alvo sem resposta) viram código de saída, como no `probe`.
"""

from dataclasses import dataclass
from datetime import datetime

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
from harness_dast.domain.authz_config import CHECK_ORDER, AuthzCheck
from harness_dast.domain.authz_plan import (
    Planned,
    plan_excessive,
    plan_horizontal,
    plan_mass_assignment,
    plan_vertical,
)
from harness_dast.domain.authz_result import AuthzResult, CheckSummary
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
    """

    product: str
    run_id: str
    checks: tuple[AuthzCheck, ...] = ()
    dry_run: bool = False
    deadline: datetime | None = None


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
        log = self._artifacts.read_exchanges(run_id)
        if probe.product != profile.product or log.product != profile.product:
            raise ConfigError(
                "A execução informada é de outro produto.",
                hint="Use o run_id do probe deste produto.",
            )
        if probe.dry_run:
            raise ConfigError(
                "O probe desta execução foi uma simulação (--dry-run): não há pedidos a repetir.",
                hint="Rode o probe sem --dry-run e use o run_id dele.",
            )
        spec = self._specs.load(request.product, profile)
        profile.authz.ensure_operations_exist([op.operation_id for op in spec.operations])
        checks = profile.authz.enabled_checks(request.checks)
        plans = _plan(profile, log.exchanges, checks)
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
            accounts=outcome.accounts,
            checks=_all_checks(outcome.checks, profile),
            findings=outcome.findings,
            not_tested=outcome.not_tested,
        )
        if not request.dry_run:
            self._artifacts.write_authz(run_id, result)
        return result

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
    profile: ProductProfile, exchanges: tuple[ExchangeRecord, ...], checks: tuple[AuthzCheck, ...]
) -> AuthzPlans:
    config = profile.authz
    roles = {account.alias: account.role for account in profile.auth.accounts}
    public = frozenset(config.public_operations)
    empty: Planned[ExchangeRecord] = Planned((), ())

    def assigned(item: ExchangeRecord) -> str | None:
        return profile.auth.explicit_account(item.operation_id, item.method, item.path)

    return AuthzPlans(
        horizontal=plan_horizontal(exchanges, roles, public)
        if "horizontal" in checks
        else Planned((), ()),
        excessive=plan_excessive(exchanges) if "excessive_data" in checks else empty,
        vertical=plan_vertical(
            exchanges,
            roles,
            config.role_order,
            assigned,
            frozenset(config.vertical_methods),
            public,
        )
        if "vertical" in checks
        else Planned((), ()),
        mass=plan_mass_assignment(exchanges, public)
        if "mass_assignment" in checks
        else Planned((), ()),
    )


def _dry_outcome(checks: tuple[AuthzCheck, ...], plans: AuthzPlans) -> AuthzOutcome:
    sizes = {
        "horizontal": plans.horizontal,
        "excessive_data": plans.excessive,
        "vertical": plans.vertical,
        "mass_assignment": plans.mass,
    }
    summaries = tuple(
        CheckSummary(
            check=check,
            status="skipped",
            candidates=len(sizes[check].tasks),
            message="Simulação (--dry-run): nada foi enviado.",
        )
        for check in checks
    )
    skipped = tuple(item for check in checks for item in sizes[check].not_tested)
    return AuthzOutcome("completed", None, summaries, (), skipped, 0, ())


def _all_checks(ran: tuple[CheckSummary, ...], profile: ProductProfile) -> tuple[CheckSummary, ...]:
    """Uma linha por verificação, na ordem fixa; as não rodadas aparecem como `disabled`."""
    by_name = {summary.check: summary for summary in ran}
    rows: list[CheckSummary] = []
    for check in CHECK_ORDER:
        if check in by_name:
            rows.append(by_name[check])
        else:
            why = (
                "desligada em authz.disabled_checks"
                if check in profile.authz.disabled_checks
                else "não pedida (--check)"
            )
            rows.append(CheckSummary(check=check, status="disabled", message=f"Não rodou: {why}."))
    return tuple(rows)
