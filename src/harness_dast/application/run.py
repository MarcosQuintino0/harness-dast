"""Caso de uso `run`: encadeia `preflight`, `probe`, `scan` e `report` num só processo.

Para no primeiro estágio que falha, com o código de saída DELE, e sempre grava `run.json`
(estágios, estados, tempos, código de saída e artefatos). Nunca roda a limpeza: o dado de teste
só é apagado por `hdast cleanup`, com confirmação humana; o resumo traz o comando exato.

Estágio opcional `authz` (ADR 0027, `--authz`): depois do `scan` e antes do `report`, repete com
outras contas os pedidos que o `probe` provou (BOLA, BFLA, dado a mais, atribuição em massa).
Sem `--authz` ele consta como `skipped` em `run.json`. Se o `authz` parar antes do fim, o
`report` ainda roda sobre o que existe e o código de saída continua sendo o do `authz`.

Prazo: `limits.max_duration_minutes` do perfil (reduzido por `--max-minutes`) vale para a
execução INTEIRA. O `run` calcula um único prazo absoluto no início do `probe` e o repassa ao
`probe` e ao `scan`; nenhum estágio recomeça a contagem.

Se o `scan` parar antes do fim (prazo, janela, login, ZAP ou alvo) e tiver gravado `scan.json`,
o `report` roda mesmo assim sobre o que foi coletado (o relatório sai marcado como parcial) e o
código de saída continua sendo o do `scan`.

Ctrl+C e a trava de emergência (`hdast stop`) encerram sem exceção: o estágio em curso para as
varreduras e remove as regras do Replacer (garantia do `scan`), o resumo é gravado e o código
é 130. Os estágios compartilham cache de tokens e orçamento de login (montados pela CLI), então
cada conta faz login uma vez.
"""

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from harness_dast.application.authz import AuthzRequest
from harness_dast.application.panel_index_ports import RunLive
from harness_dast.application.ports import Clock, KillSwitch, ProfileRepository
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.run_support import KILL_SWITCH_MESSAGE
from harness_dast.application.scan import ScanRequest
from harness_dast.application.scan_ports import PanelRefresher, RunMetricsRecorder, RunSummarySink
from harness_dast.application.stage_errors import (
    authz_stop_error,
    preflight_failure,
    probe_stop_error,
    scan_stop_error,
)
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError, UserInterrupt
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.run_summary import (
    STAGES,
    RunOptions,
    RunStatus,
    RunSummary,
    StageName,
    StageRecord,
    StageStatus,
)
from harness_dast.domain.scan_config import FailOn
from harness_dast.domain.scan_result import ScanResult

_Action = Callable[[], None]


class PreflightStage(Protocol):
    """Etapa `preflight`."""

    def execute(self, product: str) -> PreflightReport:
        """Roda as verificações."""
        ...


class ProbeStage(Protocol):
    """Etapa `probe`."""

    def execute(self, request: ProbeRequest) -> ProbeResult:
        """Roda o probe."""
        ...


class ScanStage(Protocol):
    """Etapa `scan`."""

    def execute(self, request: ScanRequest) -> ScanResult:
        """Roda a varredura."""
        ...


class AuthzStage(Protocol):
    """Etapa `authz` (opcional; ADR 0027)."""

    def execute(self, request: AuthzRequest) -> AuthzResult:
        """Roda o teste de autorização entre contas."""
        ...


class ReportStage(Protocol):
    """Etapa `report`."""

    def execute(self, request: ReportRequest) -> ReportOutcome:
        """Gera achados e relatório."""
        ...


@dataclass(frozen=True)
class RunRequest:
    """Pedido de um `run`.

    Attributes:
        product: Produto.
        seed: Semente dos geradores do `probe`.
        skip_scan: Para depois do `probe` (útil para o laço de regras de dados).
        authz: Roda o estágio `authz` (teste de autorização entre contas) depois do `scan` e
            antes do `report`. Desligado por padrão: manda requisições a mais e, na atribuição
            em massa, escreve no alvo. Com `skip_scan` o estágio também é pulado.
        fail_on: Limiar do `report` (sobrepõe o perfil).
        compare: Execução anterior para a comparação do `report`.
        max_minutes: Reduz o prazo do `scan` (conta o tempo já gasto); nunca amplia o perfil.
    """

    product: str
    seed: int | None = None
    skip_scan: bool = False
    authz: bool = False
    fail_on: FailOn | None = None
    compare: str | None = None
    max_minutes: int | None = None


@dataclass(frozen=True)
class RunResult:
    """Resultado do `run`.

    Attributes:
        summary: O que foi gravado em `run.json`.
        error: Erro que encerrou o `run`, ou `None` (sucesso, inclusive saída 1).
    """

    summary: RunSummary
    error: HarnessError | None


@dataclass
class _Progress:
    records: dict[StageName, StageRecord]
    product: str = ""
    started: datetime | None = None
    authz: bool = False
    run_id: str | None = None
    findings: dict[str, int] | None = None
    exceeds: bool = False
    error: HarnessError | None = None
    interrupted: bool = False
    deadline: datetime | None = None
    scan_stopped: bool = False
    authz_findings: dict[str, int] | None = None


class _Stop(Exception):
    """Interrompe o encadeamento depois de registrar a falha de um estágio."""


class RunPipeline:
    """Orquestra o `run` (veja o docstring do módulo)."""

    def __init__(
        self,
        *,
        profiles: ProfileRepository,
        preflight: PreflightStage,
        probe: ProbeStage,
        scan: ScanStage,
        report: ReportStage,
        sink: RunSummarySink,
        kill_switch: KillSwitch,
        clock: Clock,
        run_id_fallback: str,
        authz: AuthzStage | None = None,
        metrics: RunMetricsRecorder | None = None,
        panel: PanelRefresher | None = None,
        live: RunLive | None = None,
    ) -> None:
        """Cria o caso de uso.

        Args:
            profiles: Repositório de perfis (decide se há limpeza a sugerir).
            preflight: Etapa de conferência.
            probe: Etapa de sondagem.
            scan: Etapa de varredura.
            report: Etapa de relatório.
            sink: Onde gravar `run.json` e conferir os artefatos.
            kill_switch: Trava de emergência (distingue `hdast stop` de falha).
            clock: Relógio injetado.
            run_id_fallback: Identificador usado se nenhum estágio criou pasta de execução.
            authz: Etapa de autorização entre contas; `None` quando a CLI não a montou (pedir
                `--authz` assim é um erro de configuração).
            metrics: Gravador do `metrics.json` (ADR 0031); o `run` o refaz no fim, com o tempo
                de cada estágio (inclusive o `preflight`). `None` desliga a medição.
            panel: Gerador do painel da execução (ADR 0032); o `run` o chama por último, depois
                de gravar `run.json`. `None` desliga o painel.
            live: Página ao vivo do painel (ADR 0034): avisada a cada etapa e, no fim, regrava a
                página uma última vez. `None` desliga a página.
        """
        self._profiles = profiles
        self._authz_stage = authz
        self._stages = (preflight, probe, scan, report)
        self._sink = sink
        self._kill = kill_switch
        self._clock = clock
        self._fallback = run_id_fallback
        self._metrics = metrics
        self._panel = panel
        self._live = live

    def execute(self, request: RunRequest) -> RunResult:
        """Roda os estágios em ordem e grava `run.json`, aconteça o que acontecer.

        Raises:
            ConfigError: Só se `run.json` não puder ser gravado.
        """
        started = self._clock.now()
        progress = _Progress(
            records={name: StageRecord(name=name, status="not_run") for name in STAGES},
            product=request.product,
            started=started,
            authz=request.authz,
        )
        unexpected = True
        try:
            try:
                self._chain(request, progress, started)
            except _Stop:
                pass
            except KeyboardInterrupt:
                progress.interrupted = True
            unexpected = False
        finally:
            if unexpected:
                # Exceção que não é do harness: grava `run.json` e deixa a exceção seguir.
                self._finish(request, progress, started)
        return self._finish(request, progress, started)

    def _chain(self, request: RunRequest, progress: _Progress, started: datetime) -> None:
        preflight, probe, scan, report = self._stages
        self._stage("preflight", progress, lambda: self._preflight(preflight, request, progress))
        self._stage("probe", progress, lambda: self._probe(probe, request, progress, started))
        if request.skip_scan:
            progress.records["scan"] = StageRecord(
                name="scan", status="skipped", message="Pedido com --skip-scan."
            )
            progress.records["authz"] = StageRecord(
                name="authz",
                status="skipped",
                message=(
                    "Pedido com --skip-scan: o authz roda depois do scan e não foi executado. "
                    "Tire --skip-scan, ou rode 'hdast authz PRODUTO --run RUN_ID' sobre este "
                    "probe."
                    if request.authz
                    else "Pedido com --skip-scan."
                ),
            )
            progress.records["report"] = StageRecord(
                name="report", status="skipped", message="Sem varredura não há o que reportar."
            )
            return
        try:
            self._stage("scan", progress, lambda: self._scan(scan, request, progress, started))
        except _Stop:
            if not self._report_after_stop(progress):
                raise
            self._stage("report", progress, lambda: self._report(report, request, progress))
            raise
        self._authz_then_report(report, request, progress, started)

    def _authz_then_report(
        self, report: ReportStage, request: RunRequest, progress: _Progress, started: datetime
    ) -> None:
        if not request.authz:
            progress.records["authz"] = StageRecord(
                name="authz", status="skipped", message="Não pedido (use --authz)."
            )
        else:
            try:
                self._stage("authz", progress, lambda: self._authz(request, progress))
            except _Stop:
                # O `authz` parado deixa `authz.json` parcial; o `scan` já terminou, então o
                # relatório sai com o que existe e o erro do `authz` continua sendo o do `run`.
                if progress.interrupted:
                    raise
                self._stage("report", progress, lambda: self._report(report, request, progress))
                raise
        self._stage("report", progress, lambda: self._report(report, request, progress))

    def _authz(self, request: RunRequest, progress: _Progress) -> None:
        if self._authz_stage is None:
            raise ConfigError(
                "O estágio authz não está montado nesta execução.",
                hint="Rode 'hdast authz' separadamente ou use um run com o estágio ligado.",
            )
        result = self._authz_stage.execute(
            AuthzRequest(
                product=request.product,
                run_id=_require(progress.run_id),
                deadline=progress.deadline,
            )
        )
        counts = Counter(item.proposed_severity for item in result.findings)
        progress.authz_findings = {
            name: counts.get(name, 0) for name in ("high", "medium", "low", "informational")
        }
        error = authz_stop_error(result)
        if error is not None:
            raise error

    def _report_after_stop(self, progress: _Progress) -> bool:
        """Diz se vale gerar o relatório parcial de um `scan` que parou antes do fim."""
        if not progress.scan_stopped or progress.interrupted or progress.run_id is None:
            return False
        return "scan.json" in self._sink.existing_files(progress.run_id)

    def _announce(self, name: StageName, progress: _Progress) -> None:
        """Avisa a página ao vivo que a etapa começou (só quando a pasta da execução já existe)."""
        if self._live is None or progress.run_id is None or progress.started is None:
            return
        self._live.stage_started(
            progress.product,
            progress.run_id,
            name,
            tuple(progress.records[item] for item in STAGES),
            started=progress.started,
            authz=progress.authz,
        )

    def _stage(self, name: StageName, progress: _Progress, action: _Action) -> None:
        self._announce(name, progress)
        began = self._clock.now()
        completed = False
        try:
            action()
            completed = True
        except KeyboardInterrupt:
            self._record(progress, name, began, "interrupted", UserInterrupt(_INTERRUPTED))
            progress.interrupted = True
            raise _Stop from None
        except HarnessError as error:
            self._record(progress, name, began, "failed", error)
            # O primeiro erro é o que vale: o `report` parcial não esconde o do `scan`.
            progress.error = progress.error or error
            raise _Stop from None
        finally:
            if not completed and progress.records[name].status == "not_run":
                failure = HarnessError(
                    f"O estágio {name} falhou por um erro inesperado.",
                    hint="Veja o log em stderr; os artefatos parciais estão na pasta da execução.",
                )
                self._record(progress, name, began, "failed", failure)
                progress.error = progress.error or failure
        previous = progress.records[name]
        if previous.status == "not_run":
            self._record(progress, name, began, "ok", None)
        else:
            progress.records[name] = previous.model_copy(
                update={
                    "started_at": began.isoformat(),
                    "duration_seconds": self._since(began),
                }
            )
        if self._kill.engaged() and name in {"probe", "scan", "authz"}:
            progress.interrupted = True
            raise _Stop

    def _preflight(self, stage: PreflightStage, request: RunRequest, progress: _Progress) -> None:
        report = stage.execute(request.product)
        progress.run_id = report.run_id
        if not report.ready:
            raise preflight_failure(report)

    def _probe(
        self, stage: ProbeStage, request: RunRequest, progress: _Progress, started: datetime
    ) -> None:
        progress.deadline = self._deadline(request, started)
        result = stage.execute(
            ProbeRequest(product=request.product, seed=request.seed, deadline=progress.deadline)
        )
        progress.run_id = result.run_id
        error = probe_stop_error(result)
        if error is not None:
            raise error

    def _scan(
        self, stage: ScanStage, request: RunRequest, progress: _Progress, started: datetime
    ) -> None:
        run_id = _require(progress.run_id)
        result = stage.execute(
            ScanRequest(
                product=request.product,
                run_id=run_id,
                max_minutes=self._remaining(request.max_minutes, started),
                deadline=progress.deadline,
            )
        )
        error = scan_stop_error(result)
        if error is not None:
            progress.scan_stopped = True
            raise error

    def _report(self, stage: ReportStage, request: RunRequest, progress: _Progress) -> None:
        outcome = stage.execute(
            ReportRequest(
                product=request.product,
                run_id=_require(progress.run_id),
                compare=request.compare,
                fail_on=request.fail_on,
            )
        )
        progress.findings = dict(outcome.report.summary.by_severity)
        progress.exceeds = outcome.exceeds_threshold

    def _deadline(self, request: RunRequest, started: datetime) -> datetime:
        """Prazo único da execução: começa no início do `run` e vale para todos os estágios."""
        minutes = self._profiles.load(request.product).limits.max_duration_minutes
        if request.max_minutes is not None:
            minutes = min(minutes, request.max_minutes)
        return started + timedelta(minutes=minutes)

    def _remaining(self, total: int | None, started: datetime) -> int | None:
        if total is None:
            return None
        spent = (self._clock.now() - started).total_seconds() / 60
        return max(1, math.ceil(total - spent))

    def _since(self, began: datetime) -> float:
        return round((self._clock.now() - began).total_seconds(), 3)

    def _record(
        self,
        progress: _Progress,
        name: StageName,
        began: datetime,
        status: StageStatus,
        error: HarnessError | None,
    ) -> None:
        progress.records[name] = StageRecord(
            name=name,
            status=status,
            exit_code=int(error.exit_code) if error else 0,
            run_id=progress.run_id,
            started_at=began.isoformat(),
            duration_seconds=self._since(began),
            error_code=error.code if error else None,
            message=error.message if error else None,
        )

    def _finish(self, request: RunRequest, progress: _Progress, started: datetime) -> RunResult:
        stopped = self._kill.engaged()
        error = progress.error
        # A trava só vira 130 quando foi ela que parou o estágio (a mensagem é a dela). Com a
        # trava acionada, um erro de outra origem (alvo fora do ar, escopo violado de verdade)
        # mantém o código dele; `stop_requested` registra a trava de qualquer modo.
        by_kill = stopped and error is not None and error.message == KILL_SWITCH_MESSAGE
        interrupted = progress.interrupted or by_kill
        if interrupted:
            error = UserInterrupt(_STOPPED if stopped else _INTERRUPTED, hint=_RESUME)
        status: RunStatus = "completed"
        code = int(ExitCode.OK)
        if error is not None:
            status = "interrupted" if interrupted else "failed"
            code = int(error.exit_code)
        elif progress.exceeds:
            status, code = "findings", int(ExitCode.FINDINGS)
        run_id = progress.run_id or self._fallback
        finished = self._clock.now()
        self._record_metrics(request.product, progress, started, finished)
        summary = RunSummary(
            product=request.product,
            run_id=run_id,
            status=status,
            exit_code=code,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_seconds=round((finished - started).total_seconds(), 3),
            options=RunOptions(
                seed=request.seed,
                skip_scan=request.skip_scan,
                authz=request.authz,
                fail_on=request.fail_on,
                compare=request.compare,
                max_minutes=request.max_minutes,
            ),
            stages=tuple(progress.records[name] for name in STAGES),
            artifacts=self._sink.existing_files(run_id),
            findings_by_severity=progress.findings,
            authz_findings_by_severity=progress.authz_findings,
            stop_requested=stopped,
            cleanup_command=self._cleanup_command(request.product, progress.run_id),
        )
        self._sink.write_summary(run_id, summary)
        if self._panel is not None:
            self._panel.refresh(request.product, run_id)
        if self._live is not None and progress.run_id is not None:
            self._live.run_finished(request.product, run_id, summary)
        return RunResult(summary, error)

    def _record_metrics(
        self, product: str, progress: _Progress, started: datetime, finished: datetime
    ) -> None:
        """Refaz `metrics.json` com o tempo de cada estágio (sem pasta, nada a medir)."""
        if self._metrics is None or progress.run_id is None:
            return
        self._metrics.refresh(
            product,
            progress.run_id,
            stages=tuple(progress.records[name] for name in STAGES),
            run_window=(started.isoformat(), finished.isoformat()),
        )

    def _cleanup_command(self, product: str, run_id: str | None) -> str | None:
        if run_id is None or self._profiles.load(product).cleanup is None:
            return None
        return f"hdast cleanup {product} --run {run_id} --dry-run"


_INTERRUPTED = "Execução interrompida pela pessoa usuária."
_STOPPED = "A trava de emergência (hdast stop) encerrou a execução."
_RESUME = "Os artefatos parciais estão na pasta da execução; recrie a pilha para tentar de novo."


def _require(run_id: str | None) -> str:
    if run_id is None:
        raise HarnessError("O probe não devolveu a pasta da execução.")
    return run_id
