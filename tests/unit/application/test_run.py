"""`run`: encadeamento das etapas, parada na primeira falha, `run.json` e trava de emergência."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from types import SimpleNamespace
from typing import Literal, cast

from harness_dast.application.preflight_report import PreflightCheck, PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.run import RunPipeline, RunRequest, RunResult
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.report_model import FindingsReport, FindingsSummary
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository

RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"


def _preflight(
    *, ready: bool = True, kind: Literal["scope", "environment"] = "environment"
) -> PreflightReport:
    checks = () if ready else (PreflightCheck(id="zap", ok=False, detail="ZAP fora.", kind=kind),)
    return PreflightReport(product="demo", ready=ready, checks=checks, run_id="pre-run")


# Os resultados reais têm dezenas de campos que o encadeamento não lê; um objeto simples com os
# campos lidos (run_id, status, stop_message, summary) evita montar modelos inteiros aqui.
def _probe(status: str = "completed") -> ProbeResult:
    stop = "parou" if status != "completed" else None
    return cast(ProbeResult, SimpleNamespace(run_id=RUN_ID, status=status, stop_message=stop))


def _scan(status: str = "completed") -> ScanResult:
    stop = "parou" if status != "completed" else None
    return cast(ScanResult, SimpleNamespace(run_id=RUN_ID, status=status, stop_message=stop))


def _outcome(*, exceeds: bool = False) -> ReportOutcome:
    report = cast(
        FindingsReport,
        SimpleNamespace(summary=FindingsSummary(total=1, by_severity={"high": 1}, occurrences=1)),
    )
    return ReportOutcome(report, ("findings.json",), "high", exceeds)


@dataclass
class Sink:
    summaries: dict[str, RunSummary] = field(default_factory=dict)

    def write_summary(self, run_id: str, summary: RunSummary) -> None:
        self.summaries[run_id] = summary

    def existing_files(self, run_id: str) -> dict[str, str]:
        return {"probe.json": "probe.json"}


class Kill:
    def __init__(self) -> None:
        self.on = False

    def engaged(self) -> bool:
        return self.on


@dataclass
class Rig:
    clock: FixedClock = field(default_factory=lambda: FixedClock(utc(2026, 11, 13, 10)))
    kill: Kill = field(default_factory=Kill)
    sink: Sink = field(default_factory=Sink)
    calls: list[str] = field(default_factory=list)
    scan_requests: list[ScanRequest] = field(default_factory=list)
    report_requests: list[ReportRequest] = field(default_factory=list)
    preflight: Callable[[], PreflightReport] = _preflight
    probe: Callable[[], ProbeResult] = _probe
    scan: Callable[[], ScanResult] = _scan
    report: Callable[[], ReportOutcome] = _outcome

    def run(self, request: RunRequest | None = None, *, cleanup: bool = True) -> RunResult:
        profiles = InMemoryProfileRepository()
        profiles.add(valid_profile("demo", with_cleanup=cleanup))
        rig = self

        class _Pre:
            def execute(self, product: str) -> PreflightReport:
                rig.calls.append("preflight")
                return rig.preflight()

        class _Probe:
            def execute(self, request: ProbeRequest) -> ProbeResult:
                rig.calls.append("probe")
                rig.clock.advance_to(rig.clock.now() + timedelta(seconds=90))
                return rig.probe()

        class _Scan:
            def execute(self, request: ScanRequest) -> ScanResult:
                rig.calls.append("scan")
                rig.scan_requests.append(request)
                return rig.scan()

        class _Report:
            def execute(self, request: ReportRequest) -> ReportOutcome:
                rig.calls.append("report")
                rig.report_requests.append(request)
                return rig.report()

        pipeline = RunPipeline(
            profiles=profiles,
            preflight=_Pre(),
            probe=_Probe(),
            scan=_Scan(),
            report=_Report(),
            sink=self.sink,
            kill_switch=self.kill,
            clock=self.clock,
            run_id_fallback="fallback-run",
        )
        return pipeline.execute(request or RunRequest(product="demo"))


def _stage_status(result: RunResult) -> dict[str, str]:
    return {stage.name: stage.status for stage in result.summary.stages}


def test_run_chains_all_stages_and_writes_summary_when_everything_passes() -> None:
    rig = Rig()

    result = rig.run()

    assert rig.calls == ["preflight", "probe", "scan", "report"]
    assert result.error is None
    assert result.summary.exit_code == 0
    assert result.summary.status == "completed"
    assert result.summary.findings_by_severity == {"high": 1}
    assert rig.sink.summaries[RUN_ID] is result.summary
    assert set(_stage_status(result).values()) == {"ok"}


def test_run_suggests_the_exact_cleanup_command_but_never_runs_it() -> None:
    result = Rig().run()

    assert result.summary.cleanup_command == f"hdast cleanup demo --run {RUN_ID} --dry-run"


def test_run_has_no_cleanup_command_when_the_profile_has_no_cleanup() -> None:
    result = Rig().run(cleanup=False)

    assert result.summary.cleanup_command is None


def test_run_exits_with_findings_code_when_report_exceeds_threshold() -> None:
    rig = Rig(report=lambda: _outcome(exceeds=True))

    result = rig.run(RunRequest(product="demo", fail_on="high"))

    assert result.error is None
    assert result.summary.exit_code == 1
    assert result.summary.status == "findings"
    assert rig.report_requests[0].fail_on == "high"


def test_run_stops_at_failed_preflight_with_its_exit_code_and_writes_summary() -> None:
    rig = Rig(preflight=lambda: _preflight(ready=False, kind="scope"))

    result = rig.run()

    assert rig.calls == ["preflight"]
    assert result.summary.exit_code == 3
    assert result.summary.status == "failed"
    assert _stage_status(result) == {
        "preflight": "failed",
        "probe": "not_run",
        "scan": "not_run",
        "report": "not_run",
    }
    assert "pre-run" in rig.sink.summaries


def test_run_stops_at_probe_stop_with_its_exit_code() -> None:
    rig = Rig(probe=lambda: _probe("stopped_target_unresponsive"))

    result = rig.run()

    assert rig.calls == ["preflight", "probe"]
    assert result.summary.exit_code == 6
    assert result.summary.stages[1].error_code == "TARGET_ERROR"


def test_run_stops_at_scan_stop_with_its_exit_code() -> None:
    rig = Rig(scan=lambda: _scan("stopped_zap"))

    result = rig.run()

    assert rig.calls == ["preflight", "probe", "scan"]
    assert result.summary.exit_code == 5
    assert _stage_status(result)["report"] == "not_run"


def test_run_stops_when_a_stage_raises_a_harness_error() -> None:
    def failing() -> ReportOutcome:
        raise ConfigError("sem scan.json")

    result = Rig(report=failing).run()

    assert result.summary.exit_code == 2
    assert result.summary.stages[3].status == "failed"


def test_run_skip_scan_stops_after_probe_without_calling_scan_or_report() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", skip_scan=True))

    assert rig.calls == ["preflight", "probe"]
    assert result.summary.exit_code == 0
    assert _stage_status(result)["scan"] == "skipped"
    assert _stage_status(result)["report"] == "skipped"


def test_run_discounts_elapsed_time_from_max_minutes_given_to_scan() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", max_minutes=10))

    assert rig.scan_requests[0].max_minutes == 9


def test_run_never_gives_scan_less_than_one_minute() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", max_minutes=1))

    assert rig.scan_requests[0].max_minutes == 1


def test_run_ctrl_c_is_recorded_as_interrupted_with_exit_130() -> None:
    def interrupted() -> ScanResult:
        raise KeyboardInterrupt

    rig = Rig(scan=interrupted)

    result = rig.run()

    assert result.summary.exit_code == 130
    assert result.summary.status == "interrupted"
    assert _stage_status(result)["scan"] == "interrupted"
    assert _stage_status(result)["report"] == "not_run"
    assert RUN_ID in rig.sink.summaries


def test_run_kill_switch_during_scan_ends_with_exit_130_and_flags_the_stop() -> None:
    rig = Rig()

    def stopped_by_kill() -> ScanResult:
        rig.kill.on = True
        return _scan("stopped_window")

    rig.scan = stopped_by_kill

    result = rig.run()

    assert result.summary.exit_code == 130
    assert result.summary.stop_requested is True
    assert result.summary.status == "interrupted"
    assert "report" not in rig.calls


def test_run_reports_scope_error_when_the_window_closes_without_kill_switch() -> None:
    rig = Rig(scan=lambda: _scan("stopped_window"))

    result = rig.run()

    assert isinstance(result.error, ScopeViolation)
    assert result.summary.exit_code == 3
    assert result.summary.stop_requested is False


def test_run_summary_always_lists_the_four_stages_in_order() -> None:
    result = Rig().run()

    assert [s.name for s in result.summary.stages] == ["preflight", "probe", "scan", "report"]
