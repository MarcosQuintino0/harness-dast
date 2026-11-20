"""Contrato de espera local, sem rede nem relógio real."""

import json
import time
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.reporting.wait_marker import FileWaitMarker
from harness_dast.application.stack_models import StackLockInfo
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import wait as command
from tests.unit.domain.panel.helpers import run_summary

pytestmark = pytest.mark.contract
RUN_ID = "2026-11-13T10-00-00Z-demo-aaaa"


def invoke(capsys: pytest.CaptureFixture[str], run: str = RUN_ID) -> tuple[int, dict[str, Any]]:
    code = run_app(build_app(), ["--json", "wait", "--run", run, "--timeout", "1"])
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("HDAST_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / RUN_ID).mkdir()
    return tmp_path


def test_finished_returns_run_exit_code_in_data(
    runs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = run_summary(run_id=RUN_ID, product="demo").model_copy(
        update={"status": "findings", "exit_code": 1}
    )
    (runs / RUN_ID / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")
    code, envelope = invoke(capsys)
    assert code == 0
    assert envelope["run_id"] == RUN_ID
    assert envelope["data"] == {
        "state": "finished",
        "status": "findings",
        "exit_code": 1,
        "phase": None,
        "progress": None,
        "run_id": None,
        "lock_id": None,
    }


def test_stopped_without_result(runs: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, envelope = invoke(capsys)
    assert code == 0
    assert envelope["data"]["state"] == "stopped"
    assert envelope["data"]["exit_code"] is None


def test_missing_and_invalid_ids_fail_without_echo(
    runs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for value in ("../fora", "2026-11-13T10-00-00Z-demo-bbbb"):
        code, envelope = invoke(capsys, value)
        assert code == 2
        assert envelope["ok"] is False
        assert value not in json.dumps(envelope)


def test_running_waits_until_deadline(
    runs: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Lock:
        def inspect(self) -> StackLockInfo:
            return StackLockInfo(
                state="held",
                command="run",
                product="demo",
                lock_id="aabbccdd",
                started_at="2026-11-13T09:59:59+00:00",
                message="ativo",
            )

    now = [0.0]
    FileWaitMarker(runs, "aabbccdd").write("scan", RUN_ID)
    monkeypatch.setattr(command, "open_stack_lock", Lock)
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    code, envelope = invoke(capsys)
    assert code == 0
    assert envelope["data"]["state"] == "running"
    assert now[0] == 1


def test_corrupt_progress_fails(runs: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (runs / RUN_ID / "scan-progress.json").write_text("{", encoding="utf-8")
    code, envelope = invoke(capsys)
    assert code == 2
    assert envelope["ok"] is False


def test_wait_observes_completion_during_wait(
    runs: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Lock:
        def inspect(self) -> StackLockInfo:
            return StackLockInfo(
                state="held",
                command="run",
                product="demo",
                started_at="2026-11-13T09:59:59+00:00",
                message="ativo",
            )

    now = [0.0]

    def finish(seconds: float) -> None:
        now[0] += seconds
        summary = run_summary(run_id=RUN_ID, product="demo")
        (runs / RUN_ID / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")

    monkeypatch.setattr(command, "open_stack_lock", Lock)
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(time, "sleep", finish)
    code, envelope = invoke(capsys)
    assert code == 0
    assert envelope["data"]["state"] == "finished"


def test_product_wait_tracks_lock_and_returns_final_id(
    runs: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Lock:
        def inspect(self) -> StackLockInfo:
            return StackLockInfo(
                state="held", command="run", product="demo", lock_id="aabbccdd", message="ativo"
            )

    now = [0.0]
    marker = FileWaitMarker(runs, "aabbccdd")
    marker.write("probe", None)

    def finish(seconds: float) -> None:
        now[0] += seconds
        summary = run_summary(run_id=RUN_ID, product="demo")
        (runs / RUN_ID / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")
        marker.write("finished", RUN_ID)

    monkeypatch.setattr(command, "open_stack_lock", Lock)
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(time, "sleep", finish)
    code = run_app(build_app(), ["--json", "wait", "--product", "demo", "--timeout", "1"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["run_id"] == RUN_ID
    assert envelope["data"]["lock_id"] == "aabbccdd"
    assert envelope["data"]["state"] == "finished"


def test_product_wait_detects_abandoned_lock_without_final_result(
    runs: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Lock:
        def inspect(self) -> None:
            return None

    FileWaitMarker(runs, "aabbccdd").write("probe", None)
    monkeypatch.setattr(command, "open_stack_lock", Lock)
    code = run_app(
        build_app(), ["--json", "wait", "--product", "demo", "--lock", "aabbccdd", "--timeout", "1"]
    )
    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["data"]["state"] == "stopped"
    assert envelope["data"]["exit_code"] is None


def test_product_wait_resumes_same_lock_after_completion(
    runs: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Lock:
        def inspect(self) -> StackLockInfo:
            return StackLockInfo(
                state="held", command="run", product="demo", lock_id="deadbeef", message="ativo"
            )

    summary = run_summary(run_id=RUN_ID, product="demo")
    (runs / RUN_ID / "run.json").write_text(summary.model_dump_json(), encoding="utf-8")
    FileWaitMarker(runs, "aabbccdd").write("finished", RUN_ID)
    monkeypatch.setattr(command, "open_stack_lock", Lock)
    code = run_app(
        build_app(),
        ["--json", "wait", "--product", "demo", "--lock", "aabbccdd", "--timeout", "1"],
    )
    envelope = json.loads(capsys.readouterr().out)
    assert code == 0
    assert envelope["data"]["state"] == "finished"
    assert envelope["data"]["lock_id"] == "aabbccdd"
