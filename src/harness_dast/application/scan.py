"""Caso de uso `scan`: varredura ativa do ZAP sobre as requisições que o `probe` ensinou.

Fluxo (ADR 0022): lê `manifest.json`, `probe.json` e `audit.jsonl` da execução do `probe`;
decide com o `ScopeGuard` o que varrer (`domain.scan_plan`); com `--dry-run` só mostra o plano
(sem tocar o ZAP nem a rede). Sem ele: confere que o contexto do `probe` ainda existe no ZAP,
faz o login da conta, fixa limites e política ANTES da primeira varredura, instala o token no
Replacer e varre uma requisição por vez. Ao fim, MESMO com erro ou Ctrl+C, remove as regras do
Replacer e a política; depois coleta alertas e evidência já redigidos e grava `scan.json`.

O `ScanResult` devolvido nunca contém URL concreta, corpo nem segredo.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import structlog
from pydantic import ValidationError

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.panel_index_ports import ScanLive
from harness_dast.application.ports import (
    Clock,
    KillSwitch,
    ProductDocuments,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    SpecLoader,
    TargetClient,
    ZapControl,
)
from harness_dast.application.run_support import AuditTrail, GuardedSender, RateLimiter, RunGate
from harness_dast.application.scan_collect import Collected, collect
from harness_dast.application.scan_health import TargetHealth
from harness_dast.application.scan_ports import ProxyAudit, RunArtifacts, ScanControl
from harness_dast.application.scan_runner import RunnerDeps, RunOutcome, ScanRunner
from harness_dast.application.scan_tokens import AccountTokens, TokenDelivery
from harness_dast.domain.errors import (
    ConfigError,
    ExternalToolError,
    HarnessError,
    PreflightError,
)
from harness_dast.domain.overrides import LimitsOverride, narrow_limits
from harness_dast.domain.probe_plan import plan_probe
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.request_encoding import join_url
from harness_dast.domain.rule_stats import RuleStatsFile
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_plan import (
    Candidate,
    ScanPlan,
    ScanSkip,
    SentRequest,
    last_sent,
    resolve_include_outcomes,
    resolve_targets,
    select_candidates,
)
from harness_dast.domain.scan_policy import ScanLimits, ScanPolicy, build_limits, build_policy
from harness_dast.domain.scan_result import (
    AppliedLimits,
    AppliedPolicy,
    HealthSummary,
    Phase,
    PlannedScan,
    ScanEntry,
    ScanProgress,
    ScanResult,
    ScanStatusName,
)
from harness_dast.domain.scan_tokens import origin_regex
from harness_dast.domain.traffic import TrafficSummary, summarize_traffic
from harness_dast.domain.zap_messages import parse_learned_request
from harness_dast.domain.zap_scope import REPLACER_RULE_PREFIX

_log = structlog.get_logger()


@dataclass(frozen=True)
class ScanRequest:
    """Pedido de um `scan`.

    Attributes:
        product: Produto.
        run_id: Execução do `probe` que alimenta a varredura.
        only: Varre só estas operações.
        include_outcomes: `None` (sem flag): vale `scan.include_outcomes` do perfil. Tupla: só
            ESCOLHE dentro do perfil (flags só reduzem, ADR 0050); vazia é só `success`.
        dry_run: Mostra o plano, sem tocar o ZAP nem o alvo e sem gravar arquivos.
        max_minutes: Reduz o prazo total (nunca acima de `limits.max_duration_minutes`).
        threads: Reduz as threads por host (nunca acima de `limits.zap_threads_per_host`).
        account: Conta imposta a TODAS as varreduras; `None` usa a conta de cada operação no
            `probe`.
        deadline: Prazo absoluto herdado do `run` encadeado (um só para a execução inteira);
            só reduz o prazo do perfil, nunca o amplia.
    """

    product: str
    run_id: str
    only: tuple[str, ...] = ()
    include_outcomes: tuple[str, ...] | None = None
    dry_run: bool = False
    max_minutes: int | None = None
    threads: int | None = None
    account: str | None = None
    deadline: datetime | None = None


@dataclass(frozen=True)
class _Prepared:
    profile: ProductProfile
    manifest: RunManifest
    probe: ProbeResult
    pinned: str | None
    default_account: str
    limits: RunLimits
    sent: dict[str, SentRequest]
    candidates: tuple[Candidate, ...]
    skipped: tuple[ScanSkip, ...]
    include_outcomes: tuple[str, ...]
    started: datetime
    deadline: datetime
    policy: ScanPolicy
    zap_limits: ScanLimits


@dataclass(frozen=True)
class _Live:
    gate: RunGate
    health: TargetHealth
    tokens: AccountTokens


class _ContinuingTrail(AuditTrail):
    """Trilha de auditoria que continua a numeração do `audit.jsonl` do `probe`."""

    def __init__(self, store: RunStore, run_id: str, clock: Clock, last_seq: int) -> None:
        super().__init__(store, run_id, clock)
        self._seq = last_seq


class Scan:
    """Orquestra o `scan` (veja o docstring do módulo)."""

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
        scanner: ScanControl,
        store: RunStore,
        artifacts: RunArtifacts,
        clock: Clock,
        sleeper: Sleeper,
        token_cache: TokenCache | None = None,
        login_budget: LoginBudget | None = None,
        kill_switch: KillSwitch | None = None,
        proxy_audit: ProxyAudit | None = None,
        live: ScanLive | None = None,
    ) -> None:
        """Cria o caso de uso com todas as portas de que precisa.

        `token_cache`, `login_budget` e `kill_switch` são compartilhados com as outras etapas
        quando o `run` encadeia tudo num processo só (cada conta faz login uma vez). `live`
        recebe o andamento (uma chamada por função) para a página ao vivo do painel.
        """
        self._profiles = profiles
        self._specs = specs
        self._documents = documents
        self._secrets = secrets
        self._vault = vault
        self._client = client
        self._zap = zap
        self._scanner = scanner
        self._store = store
        self._artifacts = artifacts
        self._clock = clock
        self._sleeper = sleeper
        self._token_cache = token_cache
        self._login_budget = login_budget
        self._kill_switch = kill_switch
        self._proxy_audit = proxy_audit
        self._live = live

    def execute(self, request: ScanRequest) -> ScanResult:
        """Executa o `scan`.

        Returns:
            O resultado, também gravado em `scan.json` (exceto no `--dry-run`). Paradas
            antecipadas voltam em `status`, com o resultado parcial.

        Raises:
            ConfigError: Execução, perfil, OpenAPI ou argumentos inválidos.
            ScopeViolation: Autorização vencida ou janela fechada na partida.
            PreflightError: ZAP indisponível ou sem o contexto do `probe`, segredo ausente ou
                login recusado.
            ExternalToolError: Não foi possível remover as regras do Replacer ao fim.
            KeyboardInterrupt: Ctrl+C (a varredura é parada e as regras, removidas).
        """
        prepared = self._prepare(request)
        if request.dry_run:
            return self._result(prepared, request, "completed", None)
        return self._execute_live(prepared, request)

    def _prepare(self, request: ScanRequest) -> _Prepared:
        started = self._clock.now()
        profile = self._profiles.load(request.product)
        profile.ensure_runnable(started)
        require_run_id(request.run_id)
        manifest = self._artifacts.read_manifest(request.run_id)
        probe = self._artifacts.read_probe(request.run_id)
        _ensure_usable(manifest, probe, profile.product)
        unknown = sorted(set(request.only) - {op.operation_id for op in probe.operations})
        if unknown:
            raise ConfigError(
                "--only cita operação desconhecida nesta execução: " + ", ".join(unknown) + ".",
                hint="Use os operation_id de probe.json (hdast spec inspect lista os do OpenAPI).",
            )
        outcomes = resolve_include_outcomes(profile.scan.include_outcomes, request.include_outcomes)
        extra = frozenset(outcomes)
        spec = self._specs.load(request.product, profile)
        flows = self._documents.load_flows(request.product)
        planned = {
            item.operation_id: item
            for item in plan_probe(spec, flows, profile.guard(), profile.environment.base_url)
        }
        sent = last_sent(self._artifacts.read_audit(request.run_id))
        candidates, skipped = select_candidates(
            probe.operations,
            planned,
            sent,
            login_path=getattr(profile.auth, "token_path", None),
            config=profile.scan,
            include_outcomes=extra,
            only=request.only,
        )
        limits = _narrow(profile.limits, request)
        own_deadline = started + timedelta(minutes=limits.max_duration_minutes)
        deadline = own_deadline if request.deadline is None else min(own_deadline, request.deadline)
        pinned = profile.select_account(request.account).alias if request.account else None
        return _Prepared(
            profile=profile,
            manifest=manifest,
            probe=probe,
            pinned=pinned,
            default_account=pinned or _probe_account(manifest) or profile.auth.accounts[0].alias,
            limits=limits,
            sent=sent,
            candidates=candidates,
            skipped=skipped,
            include_outcomes=outcomes,
            started=started,
            deadline=deadline,
            policy=build_policy(profile.scan),
            zap_limits=build_limits(limits, profile.scan),
        )

    def _execute_live(self, prep: _Prepared, request: ScanRequest) -> ScanResult:
        context_id = prep.manifest.zap_context_id
        if context_id is None:  # garantido por _ensure_usable; protege o tipo
            raise ConfigError("O manifesto do probe não tem o contexto do ZAP.")
        base_url = prep.profile.environment.base_url
        zap_version = self._check_zap(request.run_id, context_id)
        plan = self._plan(prep, base_url)
        live = self._open(prep, request)
        self._write_progress(request.run_id, "starting", len(plan.targets))
        runner = ScanRunner(self._deps(prep, request, live, context_id))
        try:
            self._configure(prep)
            outcome = runner.run(plan.targets)
        finally:
            removed = live.tokens.remove_all()
            self._drop_policy(prep.policy.name)
        self._write_progress(request.run_id, "collecting", len(plan.targets))
        collected, status, message = self._collect(request.run_id, base_url, outcome)
        result = self._result(
            prep, request, status, message, plan=plan, entries=outcome.entries
        ).model_copy(
            update={
                "alerts_total": collected.alerts_total if collected else 0,
                "alerts_by_risk": collected.by_risk if collected else {},
                "evidence_messages": collected.evidence_messages if collected else 0,
                "rules_removed": removed,
                "health": live.health.summary,
                "traffic": self._traffic(prep),
            }
        )
        self._write_rule_stats(request.run_id, zap_version, outcome)
        self._artifacts.write_scan(request.run_id, result)
        self._write_progress(request.run_id, "done", len(plan.targets), status=status)
        if not removed:
            raise ExternalToolError(
                "Não foi possível remover as regras do Replacer ao fim do scan.",
                hint=f"Remova à mão as regras do Replacer com nome começando por "
                f"{REPLACER_RULE_PREFIX} (elas carregam o token). O resultado está em scan.json.",
            )
        return result

    def _traffic(self, prep: _Prepared) -> TrafficSummary:
        if self._proxy_audit is None:
            return TrafficSummary()
        return summarize_traffic(
            self._proxy_audit.rows(),
            start=prep.started,
            end=self._clock.now(),
            limit_rps=prep.limits.requests_per_second,
            path_mode=prep.profile.scope.path_mode,
        )

    def _write_rule_stats(self, run_id: str, zap_version: str, outcome: RunOutcome) -> None:
        """Grava `rule-stats.json`; é só medição, então uma falha de escrita não falha o scan."""
        try:
            self._artifacts.write_rule_stats(
                run_id,
                RuleStatsFile(
                    run_id=run_id, zap_version=zap_version[:40], operations=outcome.rule_stats
                ),
            )
        except ConfigError as error:
            _log.error("rule_stats_write_failed", run_id=run_id, reason=error.message)

    def _check_zap(self, run_id: str, context_id: int) -> str:
        try:
            version = self._zap.version()
            self._scanner.verify_context(f"hdast-{run_id}", context_id)
        except ExternalToolError as error:
            raise PreflightError(
                f"O ZAP não está pronto para o scan: {error.message}",
                hint=error.hint or "Refaça o probe neste ZAP: o contexto da execução sumiu.",
            ) from None
        return version

    def _plan(self, prep: _Prepared, base_url: str) -> ScanPlan:
        try:
            messages = self._scanner.list_messages(base_url)
        except ExternalToolError as error:
            raise PreflightError(
                f"Não foi possível ler o histórico do ZAP: {error.message}", hint=error.hint
            ) from None
        scheme = base_url.split("://", 1)[0]
        learned = [
            item
            for message in messages
            if message.type in {None, "1"}
            for item in [parse_learned_request(message, scheme)]
            if item is not None
        ]
        plan = resolve_targets(prep.candidates, prep.sent, learned, prep.profile.guard())
        if prep.pinned is None:
            return plan
        targets = tuple(replace(target, account=prep.pinned) for target in plan.targets)
        return replace(plan, targets=targets)

    def _open(self, prep: _Prepared, request: ScanRequest) -> _Live:
        profile = prep.profile
        run_id = request.run_id
        last_seq = max((entry.seq for entry in self._artifacts.read_audit(run_id)), default=0)
        limited = profile.model_copy(update={"limits": prep.limits})
        gate = RunGate(
            limited, self._clock, prep.started, self._kill_switch, deadline=prep.deadline
        )
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._client,
            gate=gate,
            limiter=RateLimiter(prep.limits.requests_per_second, self._clock, self._sleeper),
            trail=_ContinuingTrail(self._store, run_id, self._clock, last_seq),
            clock=self._clock,
        )
        dispatcher = OperationDispatcher(
            sender,
            self._sleeper,
            profile.auth.csrf,
            login_budget=self._login_budget
            or LoginBudget(profile.login_limit, self._clock, self._sleeper),
            login_path=profile.login_path,
            token_expired=profile.token_expired_signal,
            error_codes=profile.probe.error_codes,
        )
        health = TargetHealth(
            sender=sender,
            guard=profile.guard(),
            url=join_url(profile.environment.base_url, profile.probe.health_path or "/"),
            clock=self._clock,
            sleeper=self._sleeper,
        )
        tokens = AccountTokens(lambda alias: self._delivery(prep, alias, dispatcher), self._zap)
        return _Live(gate, health, tokens)

    def _delivery(
        self, prep: _Prepared, alias: str, dispatcher: OperationDispatcher
    ) -> TokenDelivery:
        profile = prep.profile
        session = AccountSession(
            account=profile.select_account(alias),
            auth=profile.auth,
            base_url=profile.environment.base_url,
            secrets=self._secrets,
            vault=self._vault,
            client=self._client,
            dispatcher=dispatcher,
            token_cache=self._token_cache,
        )
        session.open()
        limit = profile.login_limit
        floor = math.ceil(60 / limit.max_per_minute) if limit is not None else 0
        return TokenDelivery(
            label=alias,
            session=session,
            scanner=self._scanner,
            csrf=profile.auth.csrf,
            url_regex=origin_regex(profile.environment.base_url),
            clock=self._clock,
            refresh_seconds=max(profile.scan.token_refresh_seconds, floor),
        )

    def _deps(self, prep: _Prepared, request: ScanRequest, live: _Live, context: int) -> RunnerDeps:
        return RunnerDeps(
            scanner=self._scanner,
            gate=live.gate,
            health=live.health,
            tokens=live.tokens,
            default_account=prep.default_account,
            clock=self._clock,
            sleeper=self._sleeper,
            artifacts=self._artifacts,
            run_id=request.run_id,
            context_id=context,
            policy=prep.policy,
            limits=prep.zap_limits,
            deadline=prep.deadline,
            base_url=prep.profile.environment.base_url,
            on_progress=self._live_hook(prep, request),
        )

    def _live_hook(
        self, prep: _Prepared, request: ScanRequest
    ) -> Callable[[int, int, str | None], None] | None:
        """Aviso à página ao vivo a cada função; ler a auditoria falhar nunca para a varredura."""
        live = self._live
        if live is None:
            return None

        def notify(done: int, total: int, operation_id: str | None) -> None:
            try:
                traffic: TrafficSummary | None = self._traffic(prep)
            except HarnessError as error:
                _log.info("live_traffic_unavailable", reason=error.message)
                traffic = None
            live.scan_progress(request.run_id, done, total, operation_id, traffic)

        return notify

    def _configure(self, prep: _Prepared) -> None:
        try:
            self._zap.remove_stale_rules(REPLACER_RULE_PREFIX)
            self._scanner.apply_policy(prep.policy, prep.zap_limits)
        except ExternalToolError as error:
            raise PreflightError(
                f"Não foi possível preparar o ZAP para a varredura: {error.message}",
                hint=error.hint,
            ) from None

    def _drop_policy(self, name: str) -> None:
        try:
            self._scanner.remove_scan_policy(name)
        except ExternalToolError as error:
            _log.error("scan_policy_remove_failed", policy=name, reason=error.message)

    def _collect(
        self, run_id: str, base_url: str, outcome: RunOutcome
    ) -> tuple[Collected | None, ScanStatusName, str | None]:
        if outcome.status == "stopped_zap":
            return None, outcome.status, outcome.message
        try:
            collected = collect(
                scanner=self._scanner,
                artifacts=self._artifacts,
                vault=self._vault,
                run_id=run_id,
                base_url=base_url,
            )
        except ExternalToolError as error:
            _log.error("scan_collect_failed", reason=error.message)
            return None, "stopped_zap", f"Não foi possível coletar os alertas: {error.message}"
        return collected, outcome.status, outcome.message

    def _write_progress(
        self, run_id: str, phase: Phase, total: int, *, status: str = "running"
    ) -> None:
        self._artifacts.write_progress(
            run_id,
            ScanProgress(
                run_id=run_id,
                phase=phase,
                status=status,
                total=total,
                updated_at=self._clock.now().isoformat(),
            ),
        )

    def _result(
        self,
        prep: _Prepared,
        request: ScanRequest,
        status: ScanStatusName,
        message: str | None,
        *,
        plan: ScanPlan | None = None,
        entries: tuple[ScanEntry, ...] = (),
    ) -> ScanResult:
        targets = plan.targets if plan else ()
        pending = tuple(
            ScanSkip(
                operation_id=item.operation_id,
                method=item.method,
                path=item.path,
                reason="not_run",
                message="A varredura parou antes de chegar a esta operação.",
            )
            for item in targets[len(entries) :]
        )
        if plan:
            planned = tuple(
                PlannedScan(
                    operation_id=t.operation_id,
                    method=t.method,
                    path=t.path,
                    seed_outcome=t.seed_outcome,
                )
                for t in plan.targets
            )
        else:
            planned = tuple(
                PlannedScan(
                    operation_id=c.result.operation_id,
                    method=c.result.method,
                    path=c.result.path,
                    seed_outcome=c.seed_outcome,
                )
                for c in prep.candidates
            )
        return ScanResult(
            run_id=request.run_id,
            product=prep.profile.product,
            dry_run=request.dry_run,
            status=status,
            stop_message=message,
            started_at=prep.started.isoformat(),
            finished_at=self._clock.now().isoformat(),
            policy=AppliedPolicy.from_policy(prep.policy),
            limits=AppliedLimits.from_limits(prep.limits, prep.zap_limits),
            include_outcomes=prep.include_outcomes,
            planned=planned,
            entries=entries,
            skipped=prep.skipped + (plan.skipped if plan else ()) + pending,
            learned=plan.learned if plan else (),
            health=HealthSummary(enabled=False),
        )


def _probe_account(manifest: RunManifest) -> str | None:
    return manifest.accounts[0] if manifest.accounts else None


def _ensure_usable(manifest: RunManifest, probe: ProbeResult, product: str) -> None:
    if manifest.product != product or probe.product != product:
        raise ConfigError(
            "A execução informada é de outro produto.",
            hint="Use o run_id devolvido pelo probe deste produto.",
        )
    if probe.dry_run or manifest.zap_context_id is None:
        raise ConfigError(
            "A execução informada não enviou requisições ao ZAP (foi um probe --dry-run).",
            hint="Rode o probe de verdade e use o run_id dele.",
        )


def _narrow(limits: RunLimits, request: ScanRequest) -> RunLimits:
    try:
        override = LimitsOverride(
            max_duration_minutes=request.max_minutes, zap_threads_per_host=request.threads
        )
    except ValidationError:
        raise ConfigError(
            "--max-minutes ou --threads fora do intervalo permitido.",
            hint="Use --max-minutes de 1 a 480 e --threads de 1 a 8; flags só reduzem.",
        ) from None
    return narrow_limits(limits, override)
