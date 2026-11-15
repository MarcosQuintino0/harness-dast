"""`run` com o estágio `negative` (ligado por padrão, ADR 0051): ordem, prazo, parada e resumo."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from harness_dast.application.authz import AuthzRequest
from harness_dast.application.negative import NegativeRequest
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.run import RunPipeline, RunRequest, RunResult
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.negative_result import NegativeResult
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.unit.application.test_run import RUN_ID, Kill, Sink, _outcome, _preflight, _probe, _scan
from tests.unit.application.test_run_authz import _authz
from tests.unit.domain.negative_samples import accepted, negative_result


def _negative(status: str = "completed", **changes: object) -> NegativeResult:
    return negative_result(status=status, run_id=RUN_ID, product="demo").model_copy(update=changes)


@dataclass
class Rig:
    clock: FixedClock = field(default_factory=lambda: FixedClock(utc(2026, 11, 13, 10)))
    kill: Kill = field(default_factory=Kill)
    sink: Sink = field(default_factory=Sink)
    calls: list[str] = field(default_factory=list)
    negative_requests: list[NegativeRequest] = field(default_factory=list)
    scan: Callable[[], ScanResult] = _scan
    authz: Callable[[], AuthzResult] = _authz
    negative: Callable[[], NegativeResult] = _negative
    wire_negative: bool = True

    def run(self, request: RunRequest) -> RunResult:
        profiles = InMemoryProfileRepository()
        profiles.add(valid_profile("demo"))
        rig = self

        class _Pre:
            def execute(self, product: str) -> PreflightReport:
                rig.calls.append("preflight")
                return _preflight()

        class _Probe:
            def execute(self, request: ProbeRequest) -> ProbeResult:
                rig.calls.append("probe")
                rig.clock.advance_to(rig.clock.now() + timedelta(seconds=90))
                return _probe()

        class _Scan:
            def execute(self, request: ScanRequest) -> ScanResult:
                rig.calls.append("scan")
                return rig.scan()

        class _Authz:
            def execute(self, request: AuthzRequest) -> AuthzResult:
                rig.calls.append("authz")
                return rig.authz()

        class _Negative:
            def execute(self, request: NegativeRequest) -> NegativeResult:
                rig.calls.append("negative")
                rig.negative_requests.append(request)
                return rig.negative()

        class _Report:
            def execute(self, request: ReportRequest) -> ReportOutcome:
                rig.calls.append("report")
                return _outcome()

        return RunPipeline(
            profiles=profiles,
            preflight=_Pre(),
            probe=_Probe(),
            scan=_Scan(),
            report=_Report(),
            sink=self.sink,
            kill_switch=self.kill,
            clock=self.clock,
            run_id_fallback="fallback-run",
            authz=_Authz(),
            negative=_Negative() if self.wire_negative else None,
        ).execute(request)


def _status(result: RunResult) -> dict[str, str]:
    return {stage.name: stage.status for stage in result.summary.stages}


def test_negative_runs_after_the_authz_and_before_the_report() -> None:
    rig = Rig(negative=lambda: _negative(findings=(accepted(severity="medium"),)))

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "negative", "report"]
    assert result.error is None
    assert _status(result)["negative"] == "ok"
    assert result.summary.options.negative is True
    assert result.summary.negative_findings_by_severity == {
        "high": 0,
        "medium": 1,
        "low": 0,
        "informational": 0,
    }


def test_negative_runs_by_default_without_any_flag() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo"))

    assert "negative" in rig.calls
    assert _status(result)["negative"] == "ok"


def test_no_negative_skips_the_stage_and_says_why() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", negative=False))

    assert "negative" not in rig.calls
    assert rig.calls[-2:] == ["authz", "report"]
    assert _status(result)["negative"] == "skipped"
    assert "--no-negative" in (result.summary.stages[4].message or "")
    assert result.summary.options.negative is False
    assert result.summary.negative_findings_by_severity is None


def test_no_negative_does_not_skip_the_authz() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", negative=False))

    assert _status(result)["authz"] == "ok"


def test_the_stage_shares_the_run_deadline_and_tolerates_missing_exchanges() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", max_minutes=20))

    (request,) = rig.negative_requests
    assert request.run_id == RUN_ID
    assert request.deadline is not None
    assert request.tolerate_missing_exchanges is True
    assert request.dry_run is False
    assert request.only == ()
    assert request.max_requests is None


def test_skip_scan_also_skips_the_negative_stage_and_points_to_the_standalone_command() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", skip_scan=True))

    assert rig.calls == ["preflight", "probe"]
    assert _status(result)["negative"] == "skipped"
    message = result.summary.stages[4].message or ""
    assert "--skip-scan" in message
    assert "hdast negative PRODUTO --run RUN_ID" in message


def test_skip_scan_with_no_negative_keeps_the_short_skip_message() -> None:
    result = Rig().run(RunRequest(product="demo", negative=False, skip_scan=True))

    assert result.summary.stages[4].message == "Pedido com --skip-scan e --no-negative."


def test_a_stopped_negative_still_produces_the_report_and_keeps_its_own_exit_code() -> None:
    rig = Rig(negative=lambda: _negative("stopped_deadline"))

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "negative", "report"]
    assert result.summary.exit_code == int(ExitCode.SCOPE)
    assert _status(result)["negative"] == "failed"
    assert _status(result)["report"] == "ok"


def test_a_negative_result_without_findings_counts_zero_and_exits_zero() -> None:
    rig = Rig(negative=lambda: _negative(findings=()))

    result = rig.run(RunRequest(product="demo"))

    assert result.error is None
    assert result.summary.exit_code == 0
    assert result.summary.negative_findings_by_severity == {
        "high": 0,
        "medium": 0,
        "low": 0,
        "informational": 0,
    }


def test_a_stopped_authz_stops_the_chain_before_the_negative_but_the_report_runs() -> None:
    rig = Rig(authz=lambda: _authz("stopped_deadline"))

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "report"]
    assert _status(result)["authz"] == "failed"
    assert _status(result)["negative"] == "not_run"


def test_a_failed_scan_never_reaches_the_negative_stage() -> None:
    rig = Rig(scan=lambda: _scan("stopped_zap", "ZAP caiu"))

    result = rig.run(RunRequest(product="demo"))

    assert "negative" not in rig.calls
    assert _status(result)["negative"] == "not_run"


def test_asking_for_negative_without_the_stage_wired_is_a_config_error() -> None:
    rig = Rig(wire_negative=False)

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.USAGE)
    assert _status(result)["negative"] == "failed"


def test_the_kill_switch_after_the_negative_stage_interrupts_the_run() -> None:
    rig = Rig()
    original = rig.negative

    def engage() -> NegativeResult:
        rig.kill.on = True
        return original()

    rig.negative = engage

    result = rig.run(RunRequest(product="demo"))

    assert result.summary.exit_code == int(ExitCode.INTERRUPTED)
    assert result.summary.stop_requested is True
    assert "report" not in rig.calls
