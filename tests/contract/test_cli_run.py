"""Contrato de `hdast run`: envelope JSON, códigos de saída e `run.json`.

O encadeamento em si é testado em `tests/unit/application/test_run.py`; aqui a montagem da CLI é
trocada por um `RunPipeline` falso para provar só o contrato: o `data` é o `run.json`, `ok` e
`error` seguem o código de saída, e `--json` vale antes ou depois do comando.
"""

import json
from dataclasses import dataclass
from typing import Any

import pytest

from harness_dast.application.run import RunRequest, RunResult
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import run as run_command
from harness_dast.domain.errors import ExitCode, HarnessError, ScopeViolation, UserInterrupt
from harness_dast.domain.run_summary import RunOptions, RunStatus, RunSummary, StageRecord

pytestmark = pytest.mark.contract

SUMMARY_KEYS = {
    "schema_version",
    "product",
    "run_id",
    "status",
    "exit_code",
    "started_at",
    "finished_at",
    "duration_seconds",
    "options",
    "stages",
    "artifacts",
    "findings_by_severity",
    "authz_findings_by_severity",
    "negative_findings_by_severity",
    "stop_requested",
    "cleanup_command",
}
RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"


def _summary(status: RunStatus, code: int, *, stop: bool = False) -> RunSummary:
    names = ("preflight", "probe", "scan", "authz", "negative", "report")
    return RunSummary(
        product="demo",
        run_id=RUN_ID,
        status=status,
        exit_code=code,
        started_at="2026-11-13T10:00:00+00:00",
        finished_at="2026-11-13T10:01:00+00:00",
        duration_seconds=60.0,
        options=RunOptions(),
        stages=tuple(StageRecord(name=n, status="ok") for n in names),  # type: ignore[arg-type]  # nomes literais
        artifacts={"probe.json": "probe.json"},
        findings_by_severity={"high": 1},
        stop_requested=stop,
        cleanup_command=f"hdast cleanup demo --run {RUN_ID} --dry-run",
    )


SEEN: list[RunRequest] = []


@dataclass
class _Pipeline:
    result: RunResult

    def execute(self, request: RunRequest) -> RunResult:
        SEEN.append(request)
        return self.result


class _Net:
    def close(self) -> None:
        return None


def _install(monkeypatch: pytest.MonkeyPatch, result: RunResult) -> None:
    monkeypatch.setattr(run_command, "open_scan_network", lambda *a, **k: _Net())
    monkeypatch.setattr(run_command, "build_run_pipeline", lambda *a, **k: _Pipeline(result))


def _call(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = run_app(build_app(), [*args])
    out = capsys.readouterr().out
    return code, json.loads(out)


@pytest.mark.parametrize(
    ("status", "code", "error"),
    [
        ("completed", 0, None),
        ("findings", 1, None),
        ("failed", 3, ScopeViolation("janela fechada")),
        ("interrupted", 130, UserInterrupt("interrompida")),
    ],
)
def test_run_envelope_data_is_the_run_summary_and_exit_code_follows_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: RunStatus,
    code: int,
    error: HarnessError | None,
) -> None:
    _install(monkeypatch, RunResult(_summary(status, code), error))

    exit_code, envelope = _call(capsys, "run", "demo", "--json")

    assert exit_code == code
    assert envelope["schema_version"] == 1
    assert envelope["run_id"] == RUN_ID
    assert envelope["ok"] is (error is None)
    assert set(envelope["data"]) == SUMMARY_KEYS
    assert envelope["data"]["exit_code"] == code
    assert [s["name"] for s in envelope["data"]["stages"]] == [
        "preflight",
        "probe",
        "scan",
        "authz",
        "negative",
        "report",
    ]
    if error is not None:
        assert envelope["error"]["code"] == error.code


def test_run_accepts_json_before_the_command_and_its_flags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(monkeypatch, RunResult(_summary("completed", 0), None))

    code, envelope = _call(
        capsys, "--json", "run", "demo", "--skip-scan", "--fail-on", "high", "--max-minutes", "5"
    )

    assert code == int(ExitCode.OK)
    assert envelope["ok"] is True


def test_run_rejects_an_unknown_fail_on_value_with_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, envelope = _call(capsys, "--json", "run", "demo", "--fail-on", "critical")

    assert code == int(ExitCode.USAGE)
    assert envelope["error"]["code"] == "CONFIG_ERROR"


@pytest.mark.parametrize(
    ("flags", "expected"),
    [((), True), (("--authz",), True), (("--no-authz",), False)],
)
def test_run_has_the_authz_stage_on_by_default_and_no_authz_turns_it_off(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
    expected: bool,
) -> None:
    SEEN.clear()
    _install(monkeypatch, RunResult(_summary("completed", 0), None))

    code, _ = _call(capsys, "run", "demo", "--json", *flags)

    assert code == int(ExitCode.OK)
    assert [request.authz for request in SEEN] == [expected]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [((), True), (("--negative",), True), (("--no-negative",), False)],
)
def test_run_has_the_negative_stage_on_by_default_and_no_negative_turns_it_off(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
    expected: bool,
) -> None:
    SEEN.clear()
    _install(monkeypatch, RunResult(_summary("completed", 0), None))

    code, _ = _call(capsys, "run", "demo", "--json", *flags)

    assert code == int(ExitCode.OK)
    assert [request.negative for request in SEEN] == [expected]
    assert [request.authz for request in SEEN] == [True]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [((), True), (("--include-outcomes",), True), (("--no-include-outcomes",), False)],
)
def test_run_uses_the_profile_outcomes_by_default_and_the_flag_only_reduces(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
    expected: bool,
) -> None:
    SEEN.clear()
    _install(monkeypatch, RunResult(_summary("completed", 0), None))

    code, envelope = _call(capsys, "run", "demo", "--json", *flags)

    assert code == int(ExitCode.OK)
    assert [request.include_outcomes for request in SEEN] == [expected]
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
