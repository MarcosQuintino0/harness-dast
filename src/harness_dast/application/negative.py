"""Caso de uso `negative`: teste de valores que o esquema proíbe (ADR 0051).

Fluxo: lê `probe.json` e `exchanges.json` da execução, confere perfil, janela e autorização
agora, planeja no domínio (puro) quais campos mexer e com qual valor, e, sem `--dry-run`, envia
os pedidos pelo MESMO caminho do `probe` e do `authz` (`OperationDispatcher` sobre
`GuardedSender`). Grava `negative.json`. Determinístico: não usa o ZAP, não inventa caminho, não
troca método e manda um valor proibido por pedido. Achado é dado para o agente (não vira erro do
comando); só paradas no meio (janela, prazo, ZAP, alvo sem resposta) viram código de saída.

Escrita só com a carta (`negative.allow_writes`): sem ela os pedidos de `POST`, `PUT` e `PATCH`
ficam fora do plano e aparecem em `not_tested`; nenhuma flag a liga (flags só reduzem). `DELETE`
nunca. O valor enviado nunca é gravado.

Passa de 300 linhas de propósito: é a montagem do caso de uso (portas, trilha, despachante e
sessões), no molde de `authz.py`, e o pedido, o plano e o resultado dependem dessa ordem.
"""

from dataclasses import dataclass
from datetime import datetime

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.common_ports import (
    Clock,
    KillSwitch,
    MutationJournal,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    SpecLoader,
    TargetClient,
)
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.negative_ports import NegativeArtifacts
from harness_dast.application.negative_runner import NegativeOutcome, NegativeRunner
from harness_dast.application.negative_sender import NegativeSender, NegativeSettings
from harness_dast.application.run_support import AuditTrail, GuardedSender, RateLimiter, RunGate
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_plan import NegativePlan, plan_negative
from harness_dast.domain.negative_result import NegativeNotTested, NegativeResult, PlannedCase
from harness_dast.domain.negative_tally import NegativeTally
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run_ref import require_run_id


@dataclass(frozen=True)
class NegativeRequest:
    """Pedido de um `negative`.

    Attributes:
        product: Nome do produto.
        run_id: Execução do `probe` (com `exchanges.json`).
        only: Operações escolhidas (`--only`); vazio testa todas. Só reduz.
        max_requests: Teto de envios (`--max-requests`); só reduz o do perfil.
        dry_run: Só planeja (os casos e o que fica sem teste); nada é enviado nem gravado.
        deadline: Prazo absoluto herdado do `run` encadeado; só reduz o prazo do perfil.
        tolerate_missing_exchanges: Usado pelo estágio do `run`: se `exchanges.json` não puder
            ser lido, o estágio não derruba a execução; devolve `not_tested` com o motivo. O
            comando `hdast negative` solto continua recusando (erro de configuração).
    """

    product: str
    run_id: str
    only: tuple[str, ...] = ()
    max_requests: int | None = None
    dry_run: bool = False
    deadline: datetime | None = None
    tolerate_missing_exchanges: bool = False


class _ContinuingTrail(AuditTrail):
    """Trilha de auditoria que continua a numeração do `audit.jsonl` da execução."""

    def __init__(self, store: RunStore, run_id: str, clock: Clock, last_seq: int) -> None:
        super().__init__(store, run_id, clock)
        self._seq = last_seq


class Negative:
    """Orquestra o `negative` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        store: RunStore,
        artifacts: NegativeArtifacts,
        clock: Clock,
        sleeper: Sleeper,
        token_cache: TokenCache | None = None,
        login_budget: LoginBudget | None = None,
        kill_switch: KillSwitch | None = None,
        mutation_journal: MutationJournal | None = None,
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
        self._mutation_journal = mutation_journal

    def execute(self, request: NegativeRequest) -> NegativeResult:
        """Executa o `negative`.

        Args:
            request: Pedido.

        Returns:
            O resultado completo. Mesmo com parada antecipada o resultado parcial é devolvido e
            gravado em `negative.json` (exceto em `--dry-run`).

        Raises:
            ConfigError: Perfil, execução ou argumentos inválidos; `probe` sem envio ou sem
                `exchanges.json`; `--only` com operação desconhecida; `--max-requests` acima
                do perfil.
            ScopeViolation: Autorização vencida ou janela fechada na partida.
        """
        started = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(started)
        run_id = require_run_id(request.run_id)
        self._check_probe(profile, run_id)
        exchanges, unavailable = self._read_exchanges(request, run_id, profile)
        spec = self._specs.load(request.product, profile)
        _ensure_only_known(request.only, spec)
        limit = profile.negative.effective_max_requests(request.max_requests)
        plan = plan_negative(
            exchanges,
            {op.operation_id: op for op in spec.operations},
            profile.negative,
            max_requests=limit,
            username_field=_username_field(profile),
            only=frozenset(request.only),
            infrastructure=profile.infrastructure_paths,
        )
        if unavailable is not None:
            plan = _unavailable(plan, unavailable)
        elif not exchanges:
            plan = _unavailable(plan, None)
        if request.dry_run:
            outcome = _dry_outcome(plan)
        else:
            if self._profiles.load(request.product) != profile:
                raise ConfigError(
                    "Perfil mudou durante a preparação do negative; recomece a etapa."
                )
            outcome = self._run(profile, request, plan, started, run_id, limit)
        result = NegativeResult(
            run_id=run_id,
            product=profile.product,
            dry_run=request.dry_run,
            status=outcome.status,
            stop_message=outcome.stop_message,
            started_at=started.isoformat(),
            finished_at=self._clock.now().isoformat(),
            requests_sent=outcome.requests_sent,
            accounts=outcome.accounts,
            created_resources=outcome.created_resources,
            restored_resources=outcome.restored_resources,
            by_class=outcome.by_class,
            operations=outcome.operations,
            operations_tested=len(outcome.operations),
            plan=_planned(plan) if request.dry_run else (),
            findings=outcome.findings,
            not_tested=outcome.not_tested,
        )
        if not request.dry_run:
            self._artifacts.write_negative(run_id, result)
        return result

    def _check_probe(self, profile: ProductProfile, run_id: str) -> None:
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

    def _read_exchanges(
        self, request: NegativeRequest, run_id: str, profile: ProductProfile
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
        if not log.exchanges and not request.tolerate_missing_exchanges:
            raise ConfigError(
                "O probe não registrou nenhum pedido com sucesso (exchanges.json vazio): não "
                "há o que testar.",
                hint="Faça o probe alcançar operações (fix-reachability) e rode de novo.",
            )
        return log.exchanges, None

    def _run(
        self,
        profile: ProductProfile,
        request: NegativeRequest,
        plan: NegativePlan,
        started: datetime,
        run_id: str,
        limit: int,
    ) -> NegativeOutcome:
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
        settings = NegativeSettings(
            base_url=profile.environment.base_url,
            dispatcher=dispatcher,
            sessions=pool,
            max_requests=limit,
            product=profile.product,
            run_id=run_id,
            clock=self._clock,
            mutation_journal=self._mutation_journal,
            credential_fields=_credential_fields(profile),
        )
        runner = NegativeRunner(
            NegativeSender(settings), product=profile.product, max_requests=limit
        )
        return runner.run(plan)

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


def _credential_fields(profile: ProductProfile) -> frozenset[str]:
    auth = profile.auth
    if isinstance(auth, PasswordLoginAuth):
        return frozenset(
            (auth.username_field, auth.password_field, auth.token_response_field.rsplit(".", 1)[-1])
        )
    return frozenset({auth.header_name})


def _username_field(profile: ProductProfile) -> str | None:
    auth = profile.auth
    return auth.username_field if isinstance(auth, PasswordLoginAuth) else None


def _ensure_only_known(only: tuple[str, ...], spec: ApiSpec) -> None:
    for name in only:
        spec.get_operation(name)


def _unavailable(plan: NegativePlan, why: str | None) -> NegativePlan:
    """Sem pedido do `probe`, o estágio diz o porquê em vez de sumir."""
    if why is None:
        reason = "no_exchanges"
        message = (
            "O probe não registrou nenhum pedido com sucesso (exchanges.json vazio): não há o "
            "que testar. Faça o probe alcançar operações (fix-reachability) e rode de novo."
        )
    else:
        reason = "exchanges_unavailable"
        message = f"Os pedidos do probe não puderam ser lidos ({why}): nada foi testado."
    note = NegativeNotTested(reason=reason, message=message)
    return NegativePlan(cases=plan.cases, not_tested=(*plan.not_tested, note))


def _planned(plan: NegativePlan) -> tuple[PlannedCase, ...]:
    return tuple(
        PlannedCase(
            operation_id=case.exchange.operation_id,
            method=case.exchange.method.upper(),
            path=case.exchange.path,
            location=case.location,
            field=case.field,
            case_class=case.case_class,
            declared=case.declared,
        )
        for case in plan.cases
    )


def _dry_outcome(plan: NegativePlan) -> NegativeOutcome:
    tally = NegativeTally(plan.cases)
    return NegativeOutcome(
        status="completed",
        stop_message=None,
        requests_sent=0,
        accounts=(),
        created_resources=0,
        restored_resources=0,
        by_class=tally.by_class(),
        operations=(),
        findings=(),
        not_tested=plan.not_tested,
    )
