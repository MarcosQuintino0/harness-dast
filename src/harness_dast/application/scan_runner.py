"""Laço do `scan`: uma varredura do ZAP por requisição aprendida, com portão, saúde e token.

Antes de CADA varredura: janela, autorização e prazo (`RunGate`), saúde do alvo e renovação do
token. Durante cada uma, a cada consulta: os mesmos portões. Janela fechada, prazo esgotado,
alvo fora do ar ou login recusado PARAM a varredura em curso (`ascan/action/stop`), guardam o
que existe e voltam como `RunOutcome`; nunca são engolidos. `KeyboardInterrupt` para a varredura
e sobe. Um corte pelo teto de duração do ZAP aparece como `FINISHED` com menos de 100% e é
marcado `truncated` (spike, Q4).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from harness_dast.application.mutation_guard import begin_mutation, finish_mutation
from harness_dast.application.ports import Clock, MutationJournal, Sleeper
from harness_dast.application.run_support import DeadlineReached, RunGate, WindowClosed
from harness_dast.application.scan_health import ScanTargetDown, TargetHealth
from harness_dast.application.scan_ports import RunArtifacts, ScanControl, ScanStart
from harness_dast.application.scan_tokens import AccountTokens
from harness_dast.domain.errors import ExternalToolError, PreflightError
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.rule_stats import MAX_REASON, OperationRules
from harness_dast.domain.scan_plan import ScanTarget
from harness_dast.domain.scan_policy import POLL_SECONDS, ScanLimits, ScanPolicy, scan_cap_minutes
from harness_dast.domain.scan_result import (
    EntryOutcome,
    Phase,
    ScanEntry,
    ScanProgress,
    ScanRefused,
    ScanStatus,
    ScanStatusName,
    interpret_finish,
)

_log = structlog.get_logger()
_STOPPING = (WindowClosed, DeadlineReached, ScanTargetDown, PreflightError)
_TRUNCATED_NOTE = (
    "O ZAP encerrou a varredura com menos de 100%: teto de duração, regra pulada ou erro. "
    "A cobertura desta operação é parcial."
)


@dataclass(frozen=True)
class RunnerDeps:
    """Colaboradores e parâmetros fixos do laço.

    Attributes:
        scanner: API de varredura do ZAP.
        gate: Portão de janela, autorização e prazo.
        health: Guarda de saúde do alvo.
        tokens: Entrega do token ao ZAP, por conta.
        clock: Relógio injetado.
        sleeper: Espera injetada.
        artifacts: Armazém dos arquivos (andamento).
        default_account: Conta usada quando a requisição aprendida não registra conta.
        run_id: Execução.
        context_id: Contexto do ZAP, enviado em TODA varredura.
        policy: Política aplicada.
        limits: Limites do ZAP.
        deadline: Prazo absoluto de todas as varreduras.
        base_url: URL base do ambiente (listagem de alertas).
        on_progress: Aviso opcional (`feitas`, `total`, próxima operação ou `None` no fim) para
            a página ao vivo do painel. Quem o entrega garante que ele não levanta erro.
    """

    scanner: ScanControl
    gate: RunGate
    health: TargetHealth
    tokens: AccountTokens
    clock: Clock
    sleeper: Sleeper
    artifacts: RunArtifacts
    default_account: str
    run_id: str
    context_id: int
    policy: ScanPolicy
    limits: ScanLimits
    deadline: datetime
    base_url: str
    on_progress: Callable[[int, int, str | None], None] | None = None
    product: str = ""
    mutation_journal: MutationJournal | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Resultado do laço: varreduras feitas, o motivo do fim e a medição por regra."""

    entries: tuple[ScanEntry, ...]
    status: ScanStatusName
    message: str | None
    rule_stats: tuple[OperationRules, ...] = ()
    local_queue_seconds: float = 0.0
    authentication_seconds: float = 0.0
    finished_mutations: tuple[str, ...] = ()


@dataclass
class _State:
    entries: list[ScanEntry] = field(default_factory=list)
    rule_stats: list[OperationRules] = field(default_factory=list)
    seen_alerts: set[str] = field(default_factory=set)
    last: ScanStatus | None = None
    index: int = 0
    local_queue_seconds: float = 0.0
    authentication_seconds: float = 0.0
    finished_mutations: list[str] = field(default_factory=list)


class ScanRunner:
    """Executa as varreduras do plano, uma por vez."""

    def __init__(self, deps: RunnerDeps) -> None:
        """Cria o executor."""
        self._d = deps
        self._state = _State()

    def run(self, targets: tuple[ScanTarget, ...]) -> RunOutcome:
        """Percorre o plano até o fim ou até uma parada antecipada.

        Returns:
            As varreduras feitas (inclusive a interrompida, com `outcome` `stopped`) e o
            estado: `completed` ou `stopped_window`, `stopped_deadline`,
            `stopped_target_unresponsive`, `stopped_zap` ou `stopped_auth`.

        Raises:
            KeyboardInterrupt: Depois de parar a varredura em curso.
        """
        queued_at = self._d.clock.now()
        try:
            for index, target in enumerate(targets, start=1):
                self._state.local_queue_seconds += max(
                    0.0, (self._d.clock.now() - queued_at).total_seconds()
                )
                self._state.index = index
                self._scan_one(target, len(targets))
        except WindowClosed as error:
            return self._stopped("stopped_window", error.message)
        except DeadlineReached as error:
            return self._stopped("stopped_deadline", error.message)
        except ScanTargetDown as error:
            return self._stopped("stopped_target_unresponsive", error.message)
        except PreflightError as error:
            return self._stopped("stopped_auth", error.message)
        except ExternalToolError as error:
            return self._stopped("stopped_zap", error.message)
        self._notify(len(targets), len(targets), None)
        return self._stopped("completed", None)

    def _stopped(self, status: ScanStatusName, message: str | None) -> RunOutcome:
        return RunOutcome(
            tuple(self._state.entries),
            status,
            message,
            tuple(self._state.rule_stats),
            round(self._state.local_queue_seconds, 3),
            round(self._state.authentication_seconds, 3),
            tuple(self._state.finished_mutations),
        )

    def _notify(self, done: int, total: int, operation_id: str | None) -> None:
        if self._d.on_progress is not None:
            self._d.on_progress(done, total, operation_id)

    def _scan_one(self, target: ScanTarget, total: int) -> None:
        d = self._d
        self._progress("scanning", total, target, 0)
        self._notify(self._state.index - 1, total, target.operation_id)
        d.gate.check()
        d.health.ensure_alive()
        self._authenticate(target.account or d.default_account)
        remaining = (d.deadline - d.clock.now()).total_seconds()
        request = ScanStart(
            url=target.url,
            method=target.method,
            body=target.body,
            context_id=d.context_id,
            policy_name=d.policy.name,
            max_scan_minutes=scan_cap_minutes(d.limits, remaining),
        )
        key: str | None = None
        if d.mutation_journal is not None and target.method.upper() in {"POST", "PUT", "PATCH"}:
            key = mutation_key(
                d.product, target.operation_id, target.account or d.default_account, target.method
            )
            begin_mutation(d.mutation_journal, key)
        try:
            scan_id = d.scanner.start_scan(request)
        except ScanRefused as error:
            if key is not None and d.mutation_journal is not None:
                finish_mutation(d.mutation_journal, key, "failed")
            self._record_refused(target, error)
            return
        started = d.clock.now()
        self._state.last = None
        try:
            status = self._wait(scan_id, target, total)
        except _STOPPING:
            self._record_stop(target, scan_id, started)
            raise
        except KeyboardInterrupt:
            self._interrupt(target, scan_id, total)
            raise
        self._record(target, scan_id, status, started, stop_requested=False)
        if key is not None and status.state.upper() == "FINISHED":
            self._state.finished_mutations.append(key)

    def _authenticate(self, account: str | None = None) -> None:
        """Mede login, renovação e troca das regras de identidade, inclusive em falha."""
        started = self._d.clock.now()
        try:
            if account is not None:
                self._d.tokens.activate(account)
            self._d.tokens.refresh_if_due()
        finally:
            self._state.authentication_seconds += max(
                0.0, (self._d.clock.now() - started).total_seconds()
            )

    def _wait(self, scan_id: str, target: ScanTarget, total: int) -> ScanStatus:
        d = self._d
        while True:
            d.sleeper.sleep(POLL_SECONDS)
            d.gate.check()
            self._authenticate()
            d.health.tick()
            status = d.scanner.scan_status(scan_id)
            self._state.last = status
            self._progress("scanning", total, target, status.progress)
            if status.finished:
                return status

    def _record_refused(self, target: ScanTarget, error: ScanRefused) -> None:
        _log.warning("scan_refused", operation_id=target.operation_id, reason=error.message)
        self._state.entries.append(
            ScanEntry(
                operation_id=target.operation_id,
                method=target.method,
                path=target.path,
                message_id=target.message_id,
                seed_outcome=target.seed_outcome,
                outcome="refused",
                note=f"O ZAP recusou iniciar a varredura: {error.message}",
            )
        )

    def _record_stop(self, target: ScanTarget, scan_id: str, started: datetime) -> None:
        last = self._state.last or ScanStatus(scan_id=scan_id, state="RUNNING", progress=0)
        self._record(target, scan_id, last, started, stop_requested=True)
        self._d.scanner.stop_scan(scan_id)

    def _interrupt(self, target: ScanTarget, scan_id: str, total: int) -> None:
        self._progress("scanning", total, target, 0, status="interrupted")
        try:
            self._d.scanner.stop_scan(scan_id)
        except ExternalToolError as error:
            _log.error("scan_stop_failed", scan_id=scan_id, reason=error.message)

    def _record(
        self,
        target: ScanTarget,
        scan_id: str,
        status: ScanStatus,
        started: datetime,
        *,
        stop_requested: bool,
    ) -> None:
        d = self._d
        outcome: EntryOutcome = interpret_finish(status, stop_requested=stop_requested)
        self._state.rule_stats.append(self._rule_stats(target, scan_id))
        alert_ids = self._new_alert_ids(status)
        note = None
        if outcome == "truncated":
            note = _TRUNCATED_NOTE
        elif outcome == "stopped":
            note = "A CLI parou esta varredura (janela, prazo, alvo, login ou ZAP)."
        self._state.entries.append(
            ScanEntry(
                operation_id=target.operation_id,
                method=target.method,
                path=target.path,
                message_id=target.message_id,
                scan_id=scan_id,
                outcome=outcome,
                progress=status.progress,
                truncated=outcome == "truncated",
                duration_seconds=round((d.clock.now() - started).total_seconds(), 3),
                requests=status.requests,
                alert_count=len(alert_ids),
                alert_ids=alert_ids,
                note=note,
                seed_outcome=target.seed_outcome,
            )
        )

    def _rule_stats(self, target: ScanTarget, scan_id: str) -> OperationRules:
        """Mede as regras da varredura; falhar aqui NUNCA falha a varredura (ADR 0031)."""
        try:
            rules = self._d.scanner.scan_rules(scan_id)
        except ExternalToolError as error:
            _log.warning(
                "rule_stats_unavailable", operation_id=target.operation_id, reason=error.message
            )
            return OperationRules(
                operation_id=target.operation_id,
                scan_id=scan_id,
                unavailable_reason=error.message[:MAX_REASON],
            )
        return OperationRules(operation_id=target.operation_id, scan_id=scan_id, rules=rules)

    def _new_alert_ids(self, status: ScanStatus) -> tuple[str, ...]:
        if status.alerts <= 0:
            return ()
        current = {
            alert["id"] for alert in self._d.scanner.list_alerts(self._d.base_url) if "id" in alert
        }
        fresh = sorted(current - self._state.seen_alerts, key=lambda value: (len(value), value))
        self._state.seen_alerts |= current
        return tuple(fresh)

    def _progress(
        self,
        phase: Phase,
        total: int,
        target: ScanTarget,
        progress: int,
        *,
        status: str = "running",
    ) -> None:
        self._d.artifacts.write_progress(
            self._d.run_id,
            ScanProgress(
                run_id=self._d.run_id,
                phase=phase,
                status=status,
                index=self._state.index,
                total=total,
                operation_id=target.operation_id,
                progress=progress,
                updated_at=self._d.clock.now().isoformat(),
            ),
        )
