"""`retestar`: seleção, `--only` e `--compare` no pipeline do `run`, classificação e saída."""

from dataclasses import dataclass, field

import pytest

from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.retest import RetestRequest, RetestUseCase
from harness_dast.application.run import RunRequest, RunResult
from harness_dast.domain.errors import ConfigError, ExitCode, ScopeViolation
from harness_dast.domain.finding import Finding
from harness_dast.domain.report.model import FindingsReport, GoneFinding
from harness_dast.domain.run_summary import RunSummary
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.retest import InMemoryRetestArtifacts
from tests.fakes.verification_data import finding
from tests.unit.application.test_run import RUN_ID, Rig, _preflight
from tests.unit.domain.test_findings_triage_qa import report_with

BEFORE = "2026-11-12T10-00-00Z-demo-0001"
AFTER = "2026-11-13T10-00-00Z-demo-aaaa"


def _finding(letter: str, operation: str, severity: str = "high") -> Finding:
    return finding().model_copy(
        update={
            "fingerprint": letter * 64,
            "finding_id": f"F-{letter * 8}",
            "operation_id": operation,
            "proposed_severity": severity,
        }
    )


def _gone(item: Finding, *, scanned: bool) -> GoneFinding:
    return GoneFinding(
        fingerprint=item.fingerprint,
        finding_id=item.finding_id,
        title=item.title,
        proposed_severity=item.proposed_severity,
        method=item.method,
        path_template=item.path_template,
        operation_scanned_now=scanned,
    )


def _after(keep: list[Finding], gone: list[tuple[Finding, bool]]) -> FindingsReport:
    base = report_with(*keep, run_id=AFTER)
    return base.model_copy(
        update={"not_observed": tuple(_gone(item, scanned=flag) for item, flag in gone)}
    )


@dataclass
class _Pipeline:
    """Pipeline falso: registra o pedido e devolve um `run.json` com `findings.json`."""

    result: RunResult
    requests: list[RunRequest] = field(default_factory=list)

    def execute(self, request: RunRequest) -> RunResult:
        self.requests.append(request)
        return self.result


class _RealPipeline:
    """O `RunPipeline` real, com estágios falsos: a aprovação é conferida no `preflight`."""

    def __init__(self, rig: Rig) -> None:
        self._rig = rig

    def execute(self, request: RunRequest) -> RunResult:
        return self._rig.run(request)


def _result(*, error: ScopeViolation | None = None, code: int = 0, files: bool = True) -> RunResult:
    summary = RunSummary.model_validate(
        {
            "product": "demo",
            "run_id": AFTER,
            "status": "completed" if error is None else "failed",
            "exit_code": code,
            "started_at": "2026-11-13T10:00:00+00:00",
            "finished_at": "2026-11-13T10:01:00+00:00",
            "duration_seconds": 60.0,
            "options": {},
            "stages": [
                {"name": n, "status": "ok"}
                for n in ("preflight", "probe", "scan", "authz", "negative", "report")
            ],
            "artifacts": {"findings.json": "findings.json"} if files else {},
        }
    )
    return RunResult(summary, error)


def _case(artifacts: InMemoryRetestArtifacts, run: _Pipeline | _RealPipeline) -> RetestUseCase:
    profiles = InMemoryProfileRepository()
    profiles.add(valid_profile("demo"))
    return RetestUseCase(
        profiles=profiles,
        artifacts=artifacts,
        run=run,
        clock=FixedClock(utc(2026, 11, 13, 10)),
    )


def _fake(
    artifacts: InMemoryRetestArtifacts, result: RunResult | None = None
) -> tuple[RetestUseCase, _Pipeline]:
    pipeline = _Pipeline(result or _result())
    return _case(artifacts, pipeline), pipeline


def _request(**changes: object) -> RetestRequest:
    base: dict[str, object] = {"product": "demo", "previous_run_id": BEFORE}
    return RetestRequest(**{**base, **changes})  # type: ignore[arg-type]  # campos nomeados do teste


def test_retest_runs_the_pipeline_only_on_the_operations_of_the_chosen_findings() -> None:
    high_a = _finding("a", "getPet")
    high_b = _finding("b", "listPets")
    low = _finding("c", "x", "low")
    artifacts = InMemoryRetestArtifacts(
        {
            BEFORE: report_with(high_a, high_b, low, run_id=BEFORE),
            AFTER: _after([high_a], [(high_b, True)]),
        }
    )
    case, pipeline = _fake(artifacts)

    case.execute(_request())

    assert len(pipeline.requests) == 1
    sent = pipeline.requests[0]
    assert sent.only == ("getPet", "listPets")
    assert sent.compare == BEFORE
    assert (sent.authz, sent.negative) == (False, False)


def test_retest_classifies_reproduced_not_reproduced_and_not_tested() -> None:
    a, b, c = _finding("a", "op1"), _finding("b", "op2"), _finding("c", "op3")
    artifacts = InMemoryRetestArtifacts(
        {
            BEFORE: report_with(a, b, c, run_id=BEFORE),
            AFTER: _after([a], [(b, True), (c, False)]),
        }
    )
    case, _ = _fake(artifacts)

    outcome = case.execute(_request(fail_on="none"))

    assert outcome.report is not None
    assert [item.result for item in outcome.report.entries] == [
        "reproduced",
        "not_reproduced",
        "not_tested",
    ]
    assert artifacts.written[AFTER] == outcome.report
    assert outcome.report.previous_run_id == BEFORE
    assert outcome.report.run_id == AFTER


def test_retest_exit_is_findings_when_a_reproduced_finding_reaches_the_threshold() -> None:
    a = _finding("a", "op1")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(a, run_id=BEFORE), AFTER: _after([a], [])}
    )
    case, _ = _fake(artifacts)

    outcome = case.execute(_request(fail_on="high"))

    assert outcome.exit_code == int(ExitCode.FINDINGS)


def test_retest_exit_is_ok_when_nothing_is_reproduced_even_with_a_strict_threshold() -> None:
    a = _finding("a", "op1")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(a, run_id=BEFORE), AFTER: _after([], [(a, True)])}
    )
    case, _ = _fake(artifacts)

    outcome = case.execute(_request(fail_on="low"))

    assert outcome.exit_code == int(ExitCode.OK)


def test_retest_keeps_the_run_error_and_writes_nothing_without_findings_json() -> None:
    a = _finding("a", "op1")
    artifacts = InMemoryRetestArtifacts({BEFORE: report_with(a, run_id=BEFORE)})
    error = ScopeViolation("Escopo não aprovado.", hint="Peça a uma pessoa que aprove.")
    case, _ = _fake(artifacts, _result(error=error, code=3, files=False))

    outcome = case.execute(_request())

    assert outcome.report is None
    assert outcome.error is error
    assert outcome.exit_code == int(ExitCode.SCOPE)
    assert artifacts.written == {}


def test_retest_keeps_the_run_exit_code_when_the_run_failed_after_the_report() -> None:
    a = _finding("a", "op1")
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(a, run_id=BEFORE), AFTER: _after([a], [])}
    )
    error = ScopeViolation("Prazo.", hint="Reduza.")
    case, _ = _fake(artifacts, _result(error=error, code=3))

    outcome = case.execute(_request(fail_on="high"))

    assert outcome.exit_code == int(ExitCode.SCOPE)
    assert outcome.report is not None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"previous_run_id": "../fora"}, "inválido"),
        ({"previous_run_id": "2026-01-01T00-00-00Z-demo-bbbb"}, "findings.json"),
        ({"findings": ("z" * 64,)}, "não existem"),
        ({"max_findings": 0}, "--max"),
        ({"max_findings": 31}, "--max"),
    ],
)
def test_retest_refuses_bad_input_before_sending_anything(
    changes: dict[str, object], message: str
) -> None:
    artifacts = InMemoryRetestArtifacts({BEFORE: report_with(_finding("a", "op1"), run_id=BEFORE)})
    case, pipeline = _fake(artifacts)

    with pytest.raises(ConfigError, match=message):
        case.execute(_request(**changes))

    assert pipeline.requests == []


def test_retest_refuses_a_run_of_another_product() -> None:
    other = report_with(_finding("a", "op1"), run_id=BEFORE).model_copy(update={"product": "outro"})
    case, pipeline = _fake(InMemoryRetestArtifacts({BEFORE: other}))

    with pytest.raises(ConfigError, match="outro produto"):
        case.execute(_request())

    assert pipeline.requests == []


def test_retest_refuses_a_run_with_another_fingerprint_version() -> None:
    old = report_with(_finding("a", "op1"), run_id=BEFORE).model_copy(
        update={"fingerprint_version": 0}
    )
    case, pipeline = _fake(InMemoryRetestArtifacts({BEFORE: old}))

    with pytest.raises(ConfigError, match="fingerprint"):
        case.execute(_request())

    assert pipeline.requests == []


def test_retest_refuses_when_there_is_no_high_or_medium_finding() -> None:
    low = _finding("a", "op1", "low")
    case, pipeline = _fake(InMemoryRetestArtifacts({BEFORE: report_with(low, run_id=BEFORE)}))

    with pytest.raises(ConfigError, match="alta ou média"):
        case.execute(_request())

    assert pipeline.requests == []


def test_retest_sends_nothing_when_the_scope_is_not_approved() -> None:
    def not_approved() -> PreflightReport:
        return _preflight(ready=False, kind="scope")

    rig = Rig(preflight=not_approved)
    artifacts = InMemoryRetestArtifacts({BEFORE: report_with(_finding("a", "op1"), run_id=BEFORE)})
    case = _case(artifacts, _RealPipeline(rig))

    outcome = case.execute(_request())

    assert rig.calls == ["preflight"]
    assert outcome.report is None
    assert outcome.exit_code == int(ExitCode.SCOPE)
    assert artifacts.written == {}


def test_retest_goes_through_the_real_pipeline_with_only_and_compare() -> None:
    a = _finding("a", "op1")
    rig = Rig()
    rig.sink.files["findings.json"] = "findings.json"
    artifacts = InMemoryRetestArtifacts(
        {BEFORE: report_with(a, run_id=BEFORE), RUN_ID: _after([a], [])}
    )
    case = _case(artifacts, _RealPipeline(rig))

    outcome = case.execute(_request())

    assert rig.calls == ["preflight", "probe", "scan", "report"]
    assert rig.probe_requests[0].only == ("op1",)
    assert rig.scan_requests[0].only == ("op1",)
    assert rig.report_requests[0].compare == BEFORE
    assert outcome.report is not None


def test_retest_checks_the_profile_before_reading_findings_or_sending_anything() -> None:
    artifacts = InMemoryRetestArtifacts({BEFORE: report_with(_finding("a", "op1"), run_id=BEFORE)})
    pipeline = _Pipeline(_result())
    case = RetestUseCase(
        profiles=InMemoryProfileRepository(),
        artifacts=artifacts,
        run=pipeline,
        clock=FixedClock(utc(2026, 11, 13, 10)),
    )

    with pytest.raises(ConfigError, match="não existe"):
        case.execute(_request())

    assert pipeline.requests == []
