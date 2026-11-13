"""Caso de uso `run`: encadeia `preflight`, `probe`, `scan` e `report` num só processo.

Para no primeiro estágio que falha, com o código de saída DELE, e sempre grava `run.json`
(estágios, estados, tempos, código de saída e artefatos). Nunca roda a limpeza: o dado de teste
só é apagado por `hdast cleanup`, com confirmação humana; o resumo traz o comando exato.

Ctrl+C e a trava de emergência (`hdast stop`) encerram sem exceção: o estágio em curso para as
varreduras e remove as regras do Replacer (garantia do `scan`), o resumo é gravado e o código
é 130. Os estágios compartilham cache de tokens e orçamento de login (montados pela CLI), então
cada conta faz login uma vez.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from harness_dast.application.ports import Clock, KillSwitch, ProfileRepository
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.scan import ScanRequest
from harness_dast.application.scan_ports import RunSummarySink
from harness_dast.application.stage_errors import (
    preflight_failure,
    probe_stop_error,
    scan_stop_error,
)
from harness_dast.domain.errors import ExitCode, HarnessError, UserInterrupt
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
        fail_on: Limiar do `report` (sobrepõe o perfil).
        compare: Execução anterior para a comparação do `report`.
        max_minutes: Reduz o prazo do `scan` (conta o tempo já gasto); nunca amplia o perfil.
    """

    product: str
    seed: int | None = None
    skip_scan: bool = False
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
    run_id: str | None = None
    findings: dict[str, int] | None = None
    exceeds: bool = False
    error: HarnessError | None = None
    interrupted: bool = False


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
        """
        self._profiles = profiles
        self._stages = (preflight, probe, scan, report)
        self._sink = sink
        self._kill = kill_switch
        self._clock = clock
        self._fallback = run_id_fallback

    def execute(self, request: RunRequest) -> RunResult:
        """Roda os estágios em ordem e grava `run.json`, aconteça o que acontecer.

        Raises:
            ConfigError: Só se `run.json` não puder ser gravado.
        """
        started = self._clock.now()
        progress = _Progress(
            records={name: StageRecord(name=name, status="not_run") for name in STAGES}
        )
        try:
            self._chain(request, progress, started)
        except _Stop:
            pass
        except KeyboardInterrupt:
            progress.interrupted = True
        return self._finish(request, progress, started)

    def _chain(self, request: RunRequest, progress: _Progress, started: datetime) -> None:
        preflight, probe, scan, report = self._stages
        self._stage("preflight", progress, lambda: self._preflight(preflight, request, progress))
        self._stage("probe", progress, lambda: self._probe(probe, request, progress))
        if request.skip_scan:
            progress.records["scan"] = StageRecord(
                name="scan", status="skipped", message="Pedido com --skip-scan."
            )
            progress.records["report"] = StageRecord(
                name="report", status="skipped", message="Sem varredura não há o que reportar."
            )
            return
        self._stage("scan", progress, lambda: self._scan(scan, request, progress, started))
        self._stage("report", progress, lambda: self._report(report, request, progress))

    def _stage(self, name: StageName, progress: _Progress, action: _Action) -> None:
        began = self._clock.now()
        try:
            action()
        except KeyboardInterrupt:
            self._record(progress, name, began, "interrupted", UserInterrupt(_INTERRUPTED))
            progress.interrupted = True
            raise _Stop from None
        except HarnessError as error:
            self._record(progress, name, began, "failed", error)
            progress.error = error
            raise _Stop from None
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
        if self._kill.engaged() and name in {"probe", "scan"}:
            progress.interrupted = True
            raise _Stop

    def _preflight(self, stage: PreflightStage, request: RunRequest, progress: _Progress) -> None:
        report = stage.execute(request.product)
        progress.run_id = report.run_id
        if not report.ready:
            raise preflight_failure(report)

    def _probe(self, stage: ProbeStage, request: RunRequest, progress: _Progress) -> None:
        result = stage.execute(ProbeRequest(product=request.product, seed=request.seed))
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
            )
        )
        error = scan_stop_error(result)
        if error is not None:
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
        interrupted = progress.interrupted or (stopped and error is not None)
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
                fail_on=request.fail_on,
                compare=request.compare,
                max_minutes=request.max_minutes,
            ),
            stages=tuple(progress.records[name] for name in STAGES),
            artifacts=self._sink.existing_files(run_id),
            findings_by_severity=progress.findings,
            stop_requested=stopped,
            cleanup_command=self._cleanup_command(request.product, progress.run_id),
        )
        self._sink.write_summary(run_id, summary)
        return RunResult(summary, error)

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
