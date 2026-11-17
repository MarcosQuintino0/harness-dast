"""Orquestra confirmação conservadora com o emissor protegido e persistência incremental.

O arquivo reúne portas e montagem do caso de uso porque as travas e a ordem de persistência
precisam ser revisadas em conjunto.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from harness_dast.application.account_session import AccountSession, TokenCache
from harness_dast.application.common_ports import (
    Clock,
    KillSwitch,
    ProfileRepository,
    RunStore,
    SecretProvider,
    SecretVault,
    Sleeper,
    TargetClient,
)
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.run_support import AuditTrail, GuardedSender, RateLimiter, RunGate
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.confirmation import (
    ConfirmationPlan,
    classify_authz_confirmation,
    judge_confirmation,
    merge_confirmation_entries,
    plan_confirmation,
    recipe_targets,
    select_confirmation_findings,
)
from harness_dast.domain.errors import (
    ConfigError,
    ExternalToolError,
    PreflightError,
    ScopeViolation,
)
from harness_dast.domain.finding import Finding
from harness_dast.domain.http_messages import HttpRequest, HttpResponse, approve
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.request_encoding import join_url
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_result import ScanResult
from harness_dast.domain.verification import VerificationEntry, VerificationFile, parse_verification


class ConfirmationArtifacts(Protocol):
    """Leitura validada dos artefatos da execução existente."""

    def read_probe(self, run_id: str) -> ProbeResult:
        """Lê resultado do probe."""
        ...

    def read_scan(self, run_id: str) -> ScanResult:
        """Lê resultado do scan."""
        ...

    def read_exchanges(self, run_id: str) -> ExchangeLog:
        """Lê sementes do probe."""
        ...

    def read_findings(self, run_id: str) -> FindingsReport:
        """Lê achados do relatório."""
        ...

    def read_audit(self, run_id: str) -> tuple[AuditEntry, ...]:
        """Lê sequência anterior da auditoria."""
        ...


class ConfirmationStore(Protocol):
    """Persistência redigida e atômica do envelope da verificação."""

    def read(self) -> VerificationFile:
        """Lê e valida resultado existente."""
        ...

    def write(self, verification: VerificationFile) -> None:
        """Redige e grava resultado incremental."""
        ...


@dataclass(frozen=True)
class ConfirmationRequest:
    """Parâmetros informados ao comando; limite e identidade são validados na execução."""

    product: str
    run_id: str
    finding: str | None = None
    maximum: int = 30


@dataclass(frozen=True)
class ConfirmationDependencies:
    """Portas necessárias para controle de rede, sessão e artefatos."""

    profiles: ProfileRepository
    artifacts: ConfirmationArtifacts
    verification: ConfirmationStore
    existing: bool
    store: RunStore
    client: TargetClient
    secrets: SecretProvider
    vault: SecretVault
    clock: Clock
    sleeper: Sleeper
    kill_switch: KillSwitch
    token_cache: TokenCache
    marker: Callable[[], str]


class _ContinuingTrail(AuditTrail):
    def __init__(self, store: RunStore, run_id: str, clock: Clock, sequence: int) -> None:
        super().__init__(store, run_id, clock)
        self._seq = sequence
        self.recipe_requests = 0
        self.session_requests = 0

    def decide(self, request: HttpRequest, reason: str | None) -> int:
        """Conta reservas aprovadas, inclusive autenticação, sem valores de requisição."""
        sequence = super().decide(request, reason)
        if reason is None:
            if request.operation_id.startswith("confirm:"):
                self.recipe_requests += 1
            else:
                self.session_requests += 1
        return sequence


class Confirmation:
    """Executa receitas com controles somente após conferir autorização e procedência."""

    def __init__(self, dependencies: ConfirmationDependencies) -> None:
        """Recebe portas reais ou falsos em memória."""
        self._d = dependencies
        self._trail: _ContinuingTrail | None = None

    @property
    def traffic(self) -> tuple[int, int]:
        """Retorna pedidos da receita e da sessão, contabilizados separadamente."""
        if self._trail is None:
            return 0, 0
        return self._trail.recipe_requests, self._trail.session_requests

    def execute(self, request: ConfirmationRequest) -> VerificationFile:
        """Confirma achados e persiste cada resultado sem alterar o relatório original."""
        run_id = require_run_id(request.run_id)
        started = self._d.clock.now()
        profile = self._d.profiles.load(request.product)
        profile.ensure_runnable(started)
        probe = self._d.artifacts.read_probe(run_id)
        scan = self._d.artifacts.read_scan(run_id)
        exchanges = self._d.artifacts.read_exchanges(run_id)
        report = self._d.artifacts.read_findings(run_id)
        for artifact in (probe, scan, exchanges, report):
            if artifact.product != request.product or artifact.run_id != run_id:
                raise ConfigError("Artefatos pertencem a outra execução ou produto.")
        if probe.dry_run or scan.dry_run:
            raise ConfigError("Probe ou scan foi simulado; não há varredura comprovada.")
        candidates: tuple[Finding | AuthzFinding, ...] = report.findings
        if report.authz is not None:
            authz = report.authz
            if authz.run_id != run_id or authz.product != request.product or authz.dry_run:
                raise ConfigError("Resultado de autorização não corresponde à execução.")
            candidates += authz.findings
        selected = select_confirmation_findings(candidates, request.maximum, request.finding)
        current = self._load(request)
        dispatcher, sessions = self._network(profile, request, started)
        for finding in selected:
            if isinstance(finding, AuthzFinding):
                current = self._save(request, current, classify_authz_confirmation(finding))
                continue
            planned = plan_confirmation(
                finding, exchanges.exchanges, scan.entries, self._d.marker()
            )
            if isinstance(planned, VerificationEntry):
                entry = planned
                stopped = False
            else:
                entry, stopped = self._run(
                    planned, finding.fingerprint, dispatcher, sessions, profile
                )
            current = self._save(request, current, entry)
            if stopped:
                raise ConfigError(
                    "Confirmação interrompida; resultado parcial em verification.json.",
                    hint="Confira autorização, pilha e conectividade antes de tentar novamente.",
                )
        return current

    def _save(
        self, request: ConfirmationRequest, current: VerificationFile, entry: VerificationEntry
    ) -> VerificationFile:
        result = parse_verification(
            {
                "schema_version": 1,
                "product": request.product,
                "run_id": request.run_id,
                "entries": merge_confirmation_entries(current.entries, (entry,)),
            }
        )
        self._d.verification.write(result)
        return result

    def _load(self, request: ConfirmationRequest) -> VerificationFile:
        if self._d.existing:
            current = self._d.verification.read()
            if current.product != request.product or current.run_id != request.run_id:
                raise ConfigError("Verificação pertence a outra execução ou produto.")
            return current
        return parse_verification(
            {
                "schema_version": 1,
                "product": request.product,
                "run_id": request.run_id,
                "entries": [],
            }
        )

    def _network(
        self, profile: ProductProfile, request: ConfirmationRequest, started: datetime
    ) -> tuple[OperationDispatcher, SessionPool]:

        def revalidate() -> None:
            if self._d.profiles.load(request.product) != profile:
                raise ConfigError("Perfil mudou durante a confirmação; reinicie a etapa.")

        sequence = max(
            (entry.seq for entry in self._d.artifacts.read_audit(request.run_id)), default=0
        )
        self._trail = _ContinuingTrail(self._d.store, request.run_id, self._d.clock, sequence)
        sender = GuardedSender(
            guard=profile.guard(),
            client=self._d.client,
            gate=RunGate(
                profile, self._d.clock, started, self._d.kill_switch, revalidate=revalidate
            ),
            limiter=RateLimiter(profile.limits.requests_per_second, self._d.clock, self._d.sleeper),
            trail=self._trail,
            clock=self._d.clock,
        )
        dispatcher = OperationDispatcher(
            sender,
            self._d.sleeper,
            profile.auth.csrf,
            login_budget=LoginBudget(profile.login_limit, self._d.clock, self._d.sleeper),
            login_path=profile.login_path,
            token_expired=profile.token_expired_signal,
            error_codes=profile.probe.error_codes,
        )
        pool = SessionPool(
            lambda alias: AccountSession(
                account=profile.select_account(alias),
                auth=profile.auth,
                base_url=profile.environment.base_url,
                secrets=self._d.secrets,
                vault=self._d.vault,
                client=self._d.client,
                dispatcher=dispatcher,
                token_cache=self._d.token_cache,
            )
        )
        return dispatcher, pool

    def _run(
        self,
        plan: ConfirmationPlan,
        fingerprint: str,
        dispatcher: OperationDispatcher,
        sessions: SessionPool,
        profile: ProductProfile,
    ) -> tuple[VerificationEntry, bool]:
        responses: list[HttpResponse | None] = []
        try:
            requests = tuple(
                HttpRequest(
                    method="GET",
                    url=join_url(profile.environment.base_url, target),
                    operation_id=f"confirm:{plan.exchange.operation_id}",
                    account=plan.exchange.account,
                )
                for target in recipe_targets(plan)
            )
            for request in requests:
                approve(profile.guard(), request)
            session = sessions.get(plan.exchange.account)
            for request in requests:
                outcome = dispatcher.send(request, session, max_attempts=1, allow_reauth=False)
                responses.append(outcome.response)
                if outcome.response is None:
                    return judge_confirmation(plan, tuple(responses), fingerprint), True
        except (ScopeViolation, ExternalToolError, PreflightError, ConfigError):
            return VerificationEntry(
                fingerprint=fingerprint,
                recipe=plan.recipe,
                level="inconclusive",
                reason="Confirmação interrompida por escopo, pilha, prazo, janela ou sessão.",
            ), True
        return judge_confirmation(plan, tuple(responses), fingerprint), False
