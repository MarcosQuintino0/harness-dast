# ruff: noqa: PT018
"""QA independente do encadeamento `RunPipeline` (`application/run.py`).

Contrato (docstring do módulo): roda preflight, probe, scan e report em ordem; para no primeiro
estágio que falha, com o código de saída DELE; SEMPRE grava `run.json` ("aconteça o que
acontecer"); nunca roda a limpeza; Ctrl+C e a trava de emergência encerram sem exceção com 130;
`max_minutes` só reduz o prazo da varredura.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from harness_dast.application.run import RunPipeline, RunRequest
from harness_dast.domain.errors import (
    ConfigError,
    ExternalToolError,
    ScopeViolation,
    TargetError,
)
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.run_summary import RunSummary
from tests.fakes.cleanup_rig import cleanup_profile
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.runtime import ManualClock

RUN_ID = "2026-11-13T10-00-00Z-demo-7f3a"


class Sink:
    def __init__(self) -> None:
        self.summaries: list[RunSummary] = []

    def write_summary(self, run_id: str, summary: RunSummary) -> None:
        self.summaries.append(summary)

    def existing_files(self, run_id: str) -> dict[str, str]:
        return {"manifest": "manifest.json"}


class Kill:
    def __init__(self) -> None:
        self.on = False

    def engaged(self) -> bool:
        return self.on


class Stage:
    """Estágio falso: devolve `result` ou levanta `error`; guarda as chamadas."""

    def __init__(self, result: Any = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[Any] = []
        self.after: Any = None

    def execute(self, request: Any) -> Any:
        self.calls.append(request)
        if self.after is not None:
            self.after()
        if self.error is not None:
            raise self.error
        return self.result


OK_PREFLIGHT = SimpleNamespace(run_id=RUN_ID, ready=True)
OK_PROBE = SimpleNamespace(run_id=RUN_ID, status="completed", stop_message=None)
OK_SCAN = SimpleNamespace(status="completed", stop_message=None)


def report_outcome(exceeds: bool = False, by_severity: dict[str, int] | None = None) -> Any:
    summary = SimpleNamespace(by_severity=by_severity or {})
    return SimpleNamespace(report=SimpleNamespace(summary=summary), exceeds_threshold=exceeds)


class Rig:
    def __init__(self, profile: ProductProfile | None = None) -> None:
        self.preflight = Stage(OK_PREFLIGHT)
        self.probe = Stage(OK_PROBE)
        self.scan = Stage(OK_SCAN)
        self.report = Stage(report_outcome())
        self.sink = Sink()
        self.kill = Kill()
        self.clock = ManualClock()
        repository = InMemoryProfileRepository()
        repository.add(profile or ProductProfile.from_data(valid_profile_data("demo")))
        self.pipeline = RunPipeline(
            profiles=repository,
            preflight=self.preflight,
            probe=self.probe,
            scan=self.scan,
            report=self.report,
            sink=self.sink,
            kill_switch=self.kill,
            clock=self.clock,
            run_id_fallback="2026-11-13T09-00-00Z-demo-0000",
        )

    def run(self, **kwargs: Any) -> Any:
        return self.pipeline.execute(RunRequest(product="demo", **kwargs))


def stage_names(summary: RunSummary) -> list[tuple[str, str]]:
    return [(item.name, item.status) for item in summary.stages]


# ---------------------------------------------------------------------------- sucesso


def test_execute_runs_the_stages_in_order_and_exits_zero_when_all_pass() -> None:
    rig = Rig()

    result = rig.run()

    assert result.error is None
    assert result.summary.exit_code == 0
    assert result.summary.status == "completed"
    assert stage_names(result.summary) == [
        ("preflight", "ok"),
        ("probe", "ok"),
        ("scan", "ok"),
        ("authz", "skipped"),
        ("report", "ok"),
    ]
    assert len(rig.sink.summaries) == 1


def test_execute_exits_with_findings_code_when_report_exceeds_the_threshold() -> None:
    rig = Rig()
    rig.report.result = report_outcome(exceeds=True, by_severity={"high": 1})

    result = rig.run()

    assert result.summary.exit_code == 1
    assert result.summary.status == "findings"
    assert result.summary.findings_by_severity == {"high": 1}


def test_execute_stops_after_the_probe_and_skips_scan_and_report_when_skip_scan() -> None:
    rig = Rig()

    result = rig.run(skip_scan=True)

    assert rig.scan.calls == [] and rig.report.calls == []
    assert [status for _, status in stage_names(result.summary)] == [
        "ok",
        "ok",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert result.summary.exit_code == 0


# --------------------------------------------------------------------------- falhas


@pytest.mark.parametrize(
    ("failing", "error", "code"),
    [
        ("preflight", ScopeViolation("janela fechada"), 3),
        ("probe", ExternalToolError("zap caiu"), 5),
        ("scan", TargetError("alvo mudo"), 6),
        ("report", ConfigError("triagem inválida"), 2),
    ],
)
def test_execute_stops_at_the_first_failing_stage_with_its_own_exit_code(
    failing: str, error: Exception, code: int
) -> None:
    rig = Rig()
    getattr(rig, failing).error = error

    result = rig.run()

    assert result.summary.exit_code == code
    assert result.error is error
    names = ["preflight", "probe", "scan", "report"]
    later = names[names.index(failing) + 1 :]
    for name in later:
        assert getattr(rig, name).calls == []
    assert dict(stage_names(result.summary))[failing] == "failed"
    assert len(rig.sink.summaries) == 1


def test_execute_stops_when_preflight_is_not_ready() -> None:
    rig = Rig()
    failed = SimpleNamespace(id="zap_version", detail="ZAP fora do ar", kind="env", ok=False)
    rig.preflight.result = SimpleNamespace(run_id=None, ready=False, first_failure=lambda: failed)

    result = rig.run()

    assert result.summary.exit_code == 4
    assert rig.probe.calls == []


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("stopped_window", 3),
        ("stopped_deadline", 3),
        ("stopped_zap", 5),
        ("stopped_target_unresponsive", 6),
    ],
)
def test_execute_translates_an_early_probe_stop_into_the_matching_exit_code(
    status: str, code: int
) -> None:
    rig = Rig()
    rig.probe.result = SimpleNamespace(run_id=RUN_ID, status=status, stop_message="parou")

    result = rig.run()

    assert result.summary.exit_code == code
    assert rig.scan.calls == []


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("stopped_window", 3),
        ("stopped_deadline", 3),
        ("stopped_auth", 4),
        ("stopped_zap", 5),
        ("stopped_target_unresponsive", 6),
    ],
)
def test_execute_translates_an_early_scan_stop_into_the_matching_exit_code(
    status: str, code: int
) -> None:
    rig = Rig()
    rig.scan.result = SimpleNamespace(status=status, stop_message="parou")

    result = rig.run()

    assert result.summary.exit_code == code
    assert rig.report.calls == []


# -------------------------------------------------------------------- run.json sempre


def test_execute_still_writes_run_json_when_a_stage_raises_an_unexpected_exception() -> None:
    # O docstring promete que `run.json` é gravado "aconteça o que acontecer". Hoje só
    # `HarnessError` e `KeyboardInterrupt` são tratados em `_stage`; um bug (RuntimeError, OSError,
    # KeyError) sai de `execute` sem `run.json`: o operador perde o rastro da execução parcial.
    rig = Rig()
    rig.scan.error = RuntimeError("bug inesperado")

    with pytest.raises(RuntimeError):
        rig.run()

    assert len(rig.sink.summaries) == 1


def test_execute_raises_config_error_only_when_run_json_cannot_be_written() -> None:
    rig = Rig()

    def broken(run_id: str, summary: RunSummary) -> None:
        raise ConfigError("disco cheio")

    rig.sink.write_summary = broken  # type: ignore[method-assign]

    with pytest.raises(ConfigError):
        rig.run()


# ------------------------------------------------------------- Ctrl+C e trava (130)


def test_execute_exits_130_and_still_writes_summary_when_user_interrupts_the_scan() -> None:
    rig = Rig()
    rig.scan.error = KeyboardInterrupt()

    result = rig.run()

    assert result.summary.exit_code == 130
    assert result.summary.status == "interrupted"
    assert dict(stage_names(result.summary))["scan"] == "interrupted"
    assert rig.report.calls == []
    assert len(rig.sink.summaries) == 1


def test_execute_exits_130_and_skips_the_scan_when_kill_switch_engages_during_the_probe() -> None:
    rig = Rig()
    rig.probe.after = lambda: setattr(rig.kill, "on", True)

    result = rig.run()

    assert result.summary.exit_code == 130
    assert result.summary.stop_requested is True
    assert rig.scan.calls == [] and rig.report.calls == []


def test_execute_exits_130_when_kill_switch_engages_during_the_scan() -> None:
    rig = Rig()
    rig.scan.after = lambda: setattr(rig.kill, "on", True)

    result = rig.run()

    assert result.summary.exit_code == 130
    assert rig.report.calls == []


# ------------------------------------------------------------------ nunca limpa


def test_execute_suggests_the_cleanup_command_but_never_runs_it_when_profile_has_cleanup() -> None:
    rig = Rig(profile=cleanup_profile().model_copy(update={"product": "demo"}))

    result = rig.run()

    assert result.summary.cleanup_command == f"hdast cleanup demo --run {RUN_ID} --dry-run"
    assert "--confirm" not in (result.summary.cleanup_command or "")


def test_execute_suggests_no_cleanup_when_profile_has_no_cleanup_block() -> None:
    rig = Rig()

    assert rig.run().summary.cleanup_command is None


def test_pipeline_has_no_collaborator_that_could_run_the_cleanup() -> None:
    import inspect

    parameters = set(inspect.signature(RunPipeline.__init__).parameters)

    assert not any("cleanup" in name or "oracle" in name for name in parameters)


# --------------------------------------------------------------- --max-minutes


@pytest.mark.parametrize(
    ("requested", "elapsed_s", "expected"), [(20, 0, 20), (20, 600, 10), (20, 3600, 1)]
)
def test_execute_passes_only_the_remaining_minutes_to_the_scan(
    requested: int, elapsed_s: int, expected: int
) -> None:
    rig = Rig()
    rig.probe.after = lambda: rig.clock.advance(elapsed_s)

    rig.run(max_minutes=requested)

    assert rig.scan.calls[0].max_minutes == expected


def test_execute_does_not_impose_a_limit_when_max_minutes_is_not_requested() -> None:
    rig = Rig()

    rig.run()

    assert rig.scan.calls[0].max_minutes is None
