"""Caso de uso `probe`: uma requisição válida por operação, enviada pelo proxy do ZAP.

Fluxo (ADR 0007 e 0018): confere perfil e janela agora; lê OpenAPI, regras e encadeamento;
planeja a ordem e o que nunca será enviado; com `--dry-run` simula sem tocar a rede; sem ele,
prepara o ZAP (sessão nova, contexto restrito, regras antigas removidas) e a conta (login,
CSRF), grava o manifesto e percorre o plano. Todo resultado é dado para o agente: falhas de
operação NÃO são erros do comando. Só viram erro (código de saída) o que impede começar
(perfil inválido, janela fechada, ZAP fora do ar, login recusado); paradas no meio saem como
`status` do resultado e a CLI as traduz em código de saída.
"""

from dataclasses import dataclass
from datetime import datetime

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.ports import (
    Clock,
    EntropySource,
    ProductDocuments,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    SpecLoader,
    TargetClient,
    ValueSourceFactory,
    ZapControl,
)
from harness_dast.application.preview import RecordingSource
from harness_dast.application.probe_runner import ProbeRunner
from harness_dast.application.run_support import (
    AuditTrail,
    GuardedSender,
    RateLimiter,
    RunGate,
)
from harness_dast.application.runner_settings import RunnerSettings, RunOutcome
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.errors import ExternalToolError, HarnessError, PreflightError
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_plan import PlannedOperation, plan_probe
from harness_dast.domain.probe_result import ProbeResult, RunManifest, summarize_results
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_builder import RequestBuilder
from harness_dast.domain.run import RunId
from harness_dast.domain.unique_values import run_tag_from_run_id
from harness_dast.domain.zap_scope import (
    REPLACER_RULE_PREFIX,
    context_exclude_regexes,
    context_include_regexes,
)


@dataclass(frozen=True)
class ProbeRequest:
    """Pedido de um `probe`.

    Attributes:
        product: Nome do produto.
        seed: Semente dos geradores; `None` sorteia uma (registrada no manifesto).
        only: Operações a executar (os produtores de `flows.yml` entram junto).
        dry_run: Monta e confere o escopo, mas não envia nada nem grava arquivos.
        include_delete: Permite `DELETE` sobre recursos criados nesta execução.
        account: Apelido imposto a TODAS as operações (reduz o roteamento do perfil a uma conta);
            `None` segue `auth.default_account` e `auth.account_map`.
    """

    product: str
    seed: int | None = None
    only: tuple[str, ...] = ()
    dry_run: bool = False
    include_delete: bool = False
    account: str | None = None


@dataclass(frozen=True)
class _Run:
    request: ProbeRequest
    profile: ProductProfile
    spec: ApiSpec
    flows: FlowSpec | None
    pinned: str | None
    accounts: tuple[str, ...]
    plan: tuple[PlannedOperation, ...]
    run_id: RunId
    seed: int
    started: datetime
    builder: RequestBuilder
    recorder: RecordingSource


class Probe:
    """Orquestra o `probe` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        specs: SpecLoader,
        documents: ProductDocuments,
        secrets: SecretProvider,
        vault: SecretVault,
        client: TargetClient,
        zap: ZapControl,
        store: RunStore,
        clock: Clock,
        sleeper: Sleeper,
        entropy: EntropySource,
        value_sources: ValueSourceFactory,
        harness_version: str,
        token_cache: TokenCache | None = None,
    ) -> None:
        """Cria o caso de uso com todas as portas de que precisa.

        `token_cache` é o cache de tokens do processo, compartilhado com o `preflight`.
        """
        self._profiles = profiles
        self._specs = specs
        self._documents = documents
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._zap = zap
        self._store = store
        self._clock = clock
        self._sleeper = sleeper
        self._entropy = entropy
        self._value_sources = value_sources
        self._harness_version = harness_version
        self._token_cache = token_cache

    def execute(self, request: ProbeRequest) -> ProbeResult:
        """Executa o `probe`.

        Args:
            request: Pedido.

        Returns:
            O resultado completo. Mesmo com paradas antecipadas (`status` diferente de
            `completed`) o resultado parcial é devolvido e gravado em `probe.json`.

        Raises:
            ConfigError: Perfil, OpenAPI, regras ou argumentos inválidos.
            ScopeViolation: Autorização vencida ou janela fechada na partida.
            PreflightError: ZAP inacessível na partida, segredo ausente ou login recusado.
        """
        run = self._prepare(request)
        if request.dry_run:
            outcome = ProbeRunner(self._settings(run, None, None)).run(run.plan)
            return self._result(run, outcome)
        return self._execute_live(run)

    def _prepare(self, request: ProbeRequest) -> _Run:
        started = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(started)
        spec = self._specs.load(request.product, profile)
        rules = self._documents.load_data_rules(request.product) or DataRules(
            schema_version=1, rules=()
        )
        flows = self._documents.load_flows(request.product)
        rules.validate_against(spec)
        if flows is not None:
            flows.validate_against(spec)
        pinned = profile.select_account(request.account).alias if request.account else None
        profile.auth.ensure_operations_exist([op.operation_id for op in spec.operations])
        plan = plan_probe(
            spec,
            flows,
            profile.guard(),
            profile.environment.base_url,
            include_delete=request.include_delete,
            only=request.only,
        )
        seed = request.seed if request.seed is not None else self._entropy.seed()
        run_id = RunId.create(
            started_at=started, product=profile.product, suffix=self._entropy.hex_suffix()
        )
        recorder = RecordingSource(self._value_sources(seed, started))
        builder = RequestBuilder(rules, recorder, run_tag_from_run_id(run_id.value))
        accounts = _accounts_used(profile, plan, pinned)
        return _Run(
            request,
            profile,
            spec,
            flows,
            pinned,
            accounts,
            plan,
            run_id,
            seed,
            started,
            builder,
            recorder,
        )

    def _settings(
        self,
        run: _Run,
        dispatcher: OperationDispatcher | None,
        pool: SessionPool | None,
    ) -> RunnerSettings:
        profile = run.profile
        auth = profile.auth
        return RunnerSettings(
            operations={op.operation_id: op for op in run.spec.operations},
            flows=run.flows,
            builder=run.builder,
            recorder=run.recorder,
            guard=profile.guard(),
            base_url=profile.environment.base_url,
            account_for=lambda planned: profile.account_for(
                planned.operation_id, planned.method, planned.path, pinned=run.pinned
            ),
            success_rule=profile.probe.success.json_field_absent_or_not_equal,
            csrf=auth.csrf,
            error_codes=profile.probe.error_codes,
            login_path=profile.login_path,
            vault=self._vault,
            clock=self._clock,
            dispatcher=dispatcher,
            sessions=pool,
        )

    def _execute_live(self, run: _Run) -> ProbeResult:
        profile = run.profile
        trail = AuditTrail(self._store, run.run_id.value, self._clock)
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._client,
            gate=RunGate(profile, self._clock, run.started),
            limiter=RateLimiter(profile.limits.requests_per_second, self._clock, self._sleeper),
            trail=trail,
            clock=self._clock,
        )
        budget = LoginBudget(profile.login_limit, self._clock, self._sleeper)
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
        zap_version, context_id = self._prepare_zap(run)
        manifest = self._manifest(run, zap_version, context_id)
        self._store.write_manifest(run.run_id.value, manifest)
        try:
            for alias in run.accounts:
                pool.get(alias)
        except HarnessError:
            self._finish_manifest(run, manifest, "failed_start")
            raise
        outcome = ProbeRunner(self._settings(run, dispatcher, pool)).run(run.plan)
        result = self._result(run, outcome)
        self._store.write_probe(run.run_id.value, result)
        self._finish_manifest(run, manifest, result.status)
        return result

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

    def _prepare_zap(self, run: _Run) -> tuple[str, int]:
        scope = run.profile.scope.to_scope()
        try:
            version = self._zap.version()
            self._zap.remove_stale_rules(REPLACER_RULE_PREFIX)
            self._zap.start_session(f"hdast-{run.run_id.value}")
            context_id = self._zap.create_context(
                f"hdast-{run.run_id.value}",
                context_include_regexes(scope),
                context_exclude_regexes(scope),
            )
        except ExternalToolError as error:
            raise PreflightError(
                f"O ZAP não está pronto: {error.message}", hint=error.hint
            ) from None
        return version, context_id

    def _manifest(self, run: _Run, zap_version: str, context_id: int) -> RunManifest:
        return RunManifest(
            run_id=run.run_id.value,
            command="probe",
            product=run.profile.product,
            harness_version=self._harness_version,
            zap_version=zap_version,
            zap_context_id=context_id,
            hashes=self._documents.hashes(run.request.product, run.profile),
            limits=run.profile.limits,
            seed=run.seed,
            accounts=run.accounts,
            started_at=run.started.isoformat(),
        )

    def _finish_manifest(self, run: _Run, manifest: RunManifest, status: str) -> None:
        finished = manifest.model_copy(
            update={"finished_at": self._clock.now().isoformat(), "status": status}
        )
        self._store.write_manifest(run.run_id.value, finished)

    def _result(self, run: _Run, outcome: RunOutcome) -> ProbeResult:
        return ProbeResult(
            run_id=run.run_id.value,
            product=run.profile.product,
            dry_run=run.request.dry_run,
            status=outcome.status,
            stop_message=outcome.stop_message,
            seed=run.seed,
            started_at=run.started.isoformat(),
            finished_at=self._clock.now().isoformat(),
            summary=summarize_results(
                outcome.results, len(run.spec.operations), dry_run=run.request.dry_run
            ),
            operations=outcome.results,
        )


def _accounts_used(
    profile: ProductProfile, plan: tuple[PlannedOperation, ...], pinned: str | None
) -> tuple[str, ...]:
    """Apelidos das contas que enviarão operações do plano (sem repetição, na ordem de uso).

    A operação de login do OpenAPI sai sem sessão, então não obriga nenhuma conta a logar.
    """
    used: list[str] = []
    for planned in plan:
        is_login = planned.method == "POST" and planned.path == profile.login_path
        if planned.decision != "send" or is_login:
            continue
        alias = profile.account_for(
            planned.operation_id, planned.method, planned.path, pinned=pinned
        )
        if alias not in used:
            used.append(alias)
    return tuple(used) or (pinned or profile.select_account(None).alias,)
