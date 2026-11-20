"""`run` com o estágio `authz` (ligado por padrão, ADR 0038): ordem, prazo, parada e resumo."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from types import SimpleNamespace
from typing import cast

from harness_dast.application.authz.service import AuthzRequest
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.probe import ProbeRequest
from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.application.run import RunPipeline, RunRequest, RunResult
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.authz.findings import horizontal_finding
from harness_dast.domain.authz.result import AuthzFinding, AuthzResult
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.scan_result import ScanResult
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.unit.application.test_run import RUN_ID, Kill, Sink, _outcome, _preflight, _probe, _scan


def _finding() -> AuthzFinding:
    return horizontal_finding(
        product="demo",
        operation_id="ver",
        method="GET",
        path_template="/api/x/{id}",
        actor=("b", "r"),
        owner=("a", "r"),
        statuses=(200, 200),
    )


def _authz(status: str = "completed", findings: tuple[AuthzFinding, ...] = ()) -> AuthzResult:
    stop = "parou" if status != "completed" else None
    return cast(
        AuthzResult,
        SimpleNamespace(run_id=RUN_ID, status=status, stop_message=stop, findings=findings),
    )


@dataclass
class Rig:
    clock: FixedClock = field(default_factory=lambda: FixedClock(utc(2026, 11, 13, 10)))
    kill: Kill = field(default_factory=Kill)
    sink: Sink = field(default_factory=Sink)
    calls: list[str] = field(default_factory=list)
    authz_requests: list[AuthzRequest] = field(default_factory=list)
    scan: Callable[[], ScanResult] = _scan
    authz: Callable[[], AuthzResult] = _authz
    wire_authz: bool = True

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
                rig.authz_requests.append(request)
                return rig.authz()

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
            authz=_Authz() if self.wire_authz else None,
        ).execute(replace(request, negative=False))


def _status(result: RunResult) -> dict[str, str]:
    return {stage.name: stage.status for stage in result.summary.stages}


def test_authz_runs_after_the_scan_and_before_the_report() -> None:
    rig = Rig(authz=lambda: _authz(findings=(_finding(),)))

    result = rig.run(RunRequest(product="demo", authz=True))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "report"]
    assert result.error is None
    assert _status(result)["authz"] == "ok"
    assert result.summary.options.authz is True
    assert result.summary.authz_findings_by_severity == {
        "high": 1,
        "medium": 0,
        "low": 0,
        "informational": 0,
    }
    assert result.summary.findings_by_severity == {"high": 1}


def test_authz_runs_by_default_without_any_flag() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo"))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "report"]
    assert _status(result)["authz"] == "ok"
    assert result.summary.options.authz is True


def test_no_authz_skips_the_stage_and_says_why() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", authz=False))

    assert "authz" not in rig.calls
    assert _status(result)["authz"] == "skipped"
    assert "--no-authz" in (result.summary.stages[4].message or "")
    assert result.summary.options.authz is False
    assert result.summary.authz_findings_by_severity is None


def test_authz_shares_the_run_deadline_and_the_probe_run_folder() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo", authz=True, max_minutes=20))

    request = rig.authz_requests[0]
    assert request.run_id == RUN_ID
    assert request.deadline is not None
    assert request.dry_run is False


def test_the_stage_asks_to_tolerate_missing_exchanges_and_never_sends_checks_or_writes() -> None:
    rig = Rig()

    rig.run(RunRequest(product="demo"))

    request = rig.authz_requests[0]
    assert request.tolerate_missing_exchanges is True
    assert request.checks == ()


def test_skip_scan_also_skips_the_authz_stage() -> None:
    rig = Rig()

    result = rig.run(RunRequest(product="demo", authz=True, skip_scan=True))

    assert rig.calls == ["preflight", "probe"]
    assert _status(result)["authz"] == "skipped"
    message = result.summary.stages[4].message or ""
    assert "--skip-scan" in message
    assert "hdast authz PRODUTO --run RUN_ID" in message


def test_skip_scan_with_no_authz_keeps_the_short_skip_message() -> None:
    result = Rig().run(RunRequest(product="demo", authz=False, skip_scan=True))

    assert result.summary.stages[4].message == "Pedido com --skip-scan e --no-authz."


def test_skip_scan_by_default_still_points_to_the_standalone_authz_command() -> None:
    result = Rig().run(RunRequest(product="demo", skip_scan=True))

    assert "hdast authz PRODUTO --run RUN_ID" in (result.summary.stages[4].message or "")


def test_a_stopped_authz_still_produces_the_report_and_keeps_its_own_exit_code() -> None:
    rig = Rig(authz=lambda: _authz("stopped_deadline"))

    result = rig.run(RunRequest(product="demo", authz=True))

    assert rig.calls == ["preflight", "probe", "scan", "authz", "report"]
    assert result.summary.exit_code == int(ExitCode.SCOPE)
    assert _status(result)["authz"] == "failed"
    assert _status(result)["report"] == "ok"


def test_a_failed_scan_never_reaches_the_authz_stage() -> None:
    rig = Rig(scan=lambda: _scan("stopped_zap", "ZAP caiu"))

    result = rig.run(RunRequest(product="demo", authz=True))

    assert "authz" not in rig.calls
    assert _status(result)["authz"] == "not_run"


def test_asking_for_authz_without_the_stage_wired_is_a_config_error() -> None:
    rig = Rig(wire_authz=False)

    result = rig.run(RunRequest(product="demo", authz=True))

    assert result.summary.exit_code == int(ExitCode.USAGE)
    assert _status(result)["authz"] == "failed"


def test_the_kill_switch_after_the_authz_stage_interrupts_the_run() -> None:
    rig = Rig()
    original = rig.authz

    def engage() -> AuthzResult:
        rig.kill.on = True
        return original()

    rig.authz = engage

    result = rig.run(RunRequest(product="demo", authz=True))

    assert result.summary.exit_code == int(ExitCode.INTERRUPTED)
    assert "report" not in rig.calls
