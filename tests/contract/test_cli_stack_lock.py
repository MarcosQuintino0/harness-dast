"""Contrato da trava por pilha (ADR 0035): envelope `STACK_BUSY`, saída 8 e comandos que a tomam.

A montagem dos comandos é trocada por falsos (como em `test_cli_run.py`) para provar só o
contrato da CLI: quem toma a trava, quando solta, o que o envelope diz e que `hdast stop`
nunca é bloqueado. A trava é o arquivo real na pasta de estado isolada pelo `conftest.py`.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.storage.stack_lock import LOCK_FILE_NAME
from harness_dast.application.stack_lock import StackLockService
from harness_dast.cli import stack_lock_composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import authz as authz_cmd
from harness_dast.cli.commands import probe as probe_cmd
from harness_dast.cli.commands import run as run_cmd
from harness_dast.cli.commands import scan as scan_cmd
from harness_dast.cli.commands import stack as stack_cmd
from harness_dast.domain.errors import ConfigError, ExitCode
from harness_dast.domain.stack_lock import LockHolder, render_lock

pytestmark = pytest.mark.contract

ENVELOPE_ERROR_KEYS = {"code", "message", "hint"}
PASSED = "passou da trava"
RUN = "2026-11-14T10-00-00Z-demo-aaaa"


def lock_file() -> Path:
    return Path(os.environ["HDAST_STATE_DIR"]) / LOCK_FILE_NAME


def plant(pid: int, command: str = "run") -> None:
    holder = LockHolder(
        lock_id="0000000000ab",
        command=command,
        product="outro",
        pid=pid,
        started_at=datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    lock_file().parent.mkdir(parents=True, exist_ok=True)
    lock_file().write_text(render_lock(holder), encoding="utf-8")


def dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    child.wait()
    return child.pid


def call(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code = run_app(build_app(), ["--json", *args])
    return code, json.loads(capsys.readouterr().out)


class _Net:
    def close(self) -> None:
        return None


@dataclass
class _UseCase:
    """Falso de um caso de uso: registra que foi chamado e se a trava existia, e levanta."""

    error: BaseException = field(default_factory=lambda: ConfigError(PASSED))
    calls: int = 0
    lock_seen: list[str] = field(default_factory=list)

    def execute(self, request: object) -> object:
        self.calls += 1
        self.lock_seen.append(
            lock_file().read_text(encoding="utf-8") if lock_file().exists() else ""
        )
        raise self.error


@dataclass(frozen=True)
class Command:
    name: str
    argv: tuple[str, ...]
    dry_argv: tuple[str, ...] | None


COMMANDS = [
    Command("probe", ("probe", "demo"), ("probe", "demo", "--dry-run")),
    Command("scan", ("scan", "demo", "--run", RUN), ("scan", "demo", "--run", RUN, "--dry-run")),
    Command("authz", ("authz", "demo", "--run", RUN), ("authz", "demo", "--run", RUN, "--dry-run")),
    Command("run", ("run", "demo"), None),
]


def install(monkeypatch: pytest.MonkeyPatch, command: str, use_case: _UseCase) -> None:
    module, opener, builder = {
        "probe": (probe_cmd, "open_network", "build_probe"),
        "scan": (scan_cmd, "open_scan_network", "build_scan"),
        "authz": (authz_cmd, "open_network", "build_authz"),
        "run": (run_cmd, "open_scan_network", "build_run_pipeline"),
    }[command]
    monkeypatch.setattr(module, opener, lambda *a, **k: _Net())
    monkeypatch.setattr(module, builder, lambda *a, **k: use_case)


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_a_second_execution_is_refused_with_stack_busy_and_exit_8_when_a_live_process_holds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    use_case = _UseCase()
    install(monkeypatch, command.name, use_case)
    plant(os.getpid(), command="run")

    code, envelope = call(capsys, *command.argv)

    assert code == 8 == int(ExitCode.BUSY)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "STACK_BUSY"
    assert set(envelope["error"]) == ENVELOPE_ERROR_KEYS
    assert "`run`" in envelope["error"]["message"]
    assert "0000000000ab" in envelope["error"]["message"]
    assert "hdast stop" in envelope["error"]["hint"]
    assert use_case.calls == 0
    assert "0000000000ab" in lock_file().read_text(encoding="utf-8")


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_the_lock_is_held_during_the_command_and_released_when_it_fails_with_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    use_case = _UseCase()
    install(monkeypatch, command.name, use_case)

    code, envelope = call(capsys, *command.argv)

    assert code == int(ExitCode.USAGE)
    assert envelope["error"]["message"] == PASSED
    assert use_case.calls == 1
    held = json.loads(use_case.lock_seen[0])
    assert (held["command"], held["product"], held["pid"]) == (command.name, "demo", os.getpid())
    assert not lock_file().exists()


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_the_lock_is_released_when_the_command_raises_an_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    install(monkeypatch, command.name, _UseCase(error=RuntimeError("boom")))

    code, envelope = call(capsys, *command.argv)

    assert code == int(ExitCode.INTERNAL)
    assert envelope["error"]["code"] == "INTERNAL"
    assert not lock_file().exists()


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_the_lock_is_released_when_the_command_is_interrupted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    install(monkeypatch, command.name, _UseCase(error=KeyboardInterrupt()))

    code, envelope = call(capsys, *command.argv)

    assert code == int(ExitCode.INTERRUPTED)
    assert envelope["error"]["code"] == "INTERRUPTED"
    assert not lock_file().exists()


@pytest.mark.parametrize("command", [c for c in COMMANDS if c.dry_argv], ids=lambda c: c.name)
def test_a_dry_run_does_not_take_nor_respect_the_lock_because_it_touches_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    assert command.dry_argv is not None
    use_case = _UseCase()
    install(monkeypatch, command.name, use_case)
    plant(os.getpid(), command="run")

    code, envelope = call(capsys, *command.dry_argv)

    assert envelope["error"]["message"] == PASSED
    assert code == int(ExitCode.USAGE)
    assert use_case.calls == 1
    assert "0000000000ab" in lock_file().read_text(encoding="utf-8")  # a do outro, intacta


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_an_orphan_lock_of_a_dead_process_is_taken_over_and_then_released(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: Command
) -> None:
    use_case = _UseCase()
    install(monkeypatch, command.name, use_case)
    plant(dead_pid(), command="scan")

    code, envelope = call(capsys, *command.argv)

    assert envelope["error"]["message"] == PASSED
    assert code == int(ExitCode.USAGE)
    assert json.loads(use_case.lock_seen[0])["command"] == command.name
    assert not lock_file().exists()


@pytest.mark.parametrize("content", ["", "{", "lixo", "[]"])
def test_an_unreadable_lock_file_fails_closed_with_stack_busy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    use_case = _UseCase()
    install(monkeypatch, "probe", use_case)
    lock_file().parent.mkdir(parents=True, exist_ok=True)
    lock_file().write_text(content, encoding="utf-8")

    code, envelope = call(capsys, "probe", "demo")

    assert code == int(ExitCode.BUSY)
    assert envelope["error"]["code"] == "STACK_BUSY"
    assert "hdast stack status" in envelope["error"]["hint"]
    assert use_case.calls == 0
    assert lock_file().read_text(encoding="utf-8") == content


def test_run_takes_the_lock_once_for_the_whole_sequence_and_does_not_block_itself(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    acquisitions: list[str] = []
    real_open = stack_lock_composition.open_stack_lock

    def counting_open(environ: Any = None) -> StackLockService:
        service = real_open(environ)
        original = service.hold

        def hold(command: str, product: str) -> Any:
            acquisitions.append(command)
            return original(command, product)

        service.hold = hold  # type: ignore[method-assign]  # só conta as tomadas
        return service

    monkeypatch.setattr(stack_lock_composition, "open_stack_lock", counting_open)
    use_case = _UseCase()
    install(monkeypatch, "run", use_case)

    code, envelope = call(capsys, "run", "demo")

    assert acquisitions == ["run"]
    assert envelope["error"]["message"] == PASSED  # a execução andou; não foi `STACK_BUSY`
    assert code == int(ExitCode.USAGE)


def test_stop_is_never_blocked_by_an_occupied_stack(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    policy = tmp_path / "policy"
    policy.mkdir()
    monkeypatch.setenv("HDAST_SCOPE_POLICY_DIR", str(policy))

    class _Stopper:
        def stop_all_scans(self) -> int:
            return 1

        def close(self) -> None:
            return None

    monkeypatch.setattr(stack_cmd, "open_zap_stopper", lambda: _Stopper())
    plant(os.getpid(), command="run")

    code, envelope = call(capsys, "stop")

    assert code == int(ExitCode.OK)
    assert envelope["ok"] is True
    assert (policy / "KILL").exists()
    assert "0000000000ab" in lock_file().read_text(encoding="utf-8")  # `stop` não mexe na trava


def test_stack_status_tells_who_occupies_the_stack(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plant(os.getpid(), command="scan")

    code, envelope = call(capsys, "stack", "status")

    assert code == int(ExitCode.OK)
    lock = envelope["data"]["lock"]
    assert lock["state"] == "held"
    assert (lock["command"], lock["product"], lock["pid"]) == ("scan", "outro", os.getpid())
    assert lock["lock_id"] == "0000000000ab"


def test_stack_status_has_no_lock_when_the_stack_is_free(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, envelope = call(capsys, "stack", "status")

    assert code == int(ExitCode.OK)
    assert envelope["data"]["lock"] is None


def test_stack_up_is_refused_while_an_execution_occupies_the_stack(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("não podia montar a pilha")

    monkeypatch.setattr(stack_cmd, "build_stack_manager", refuse)
    plant(os.getpid(), command="run")

    code, envelope = call(capsys, "stack", "up", "demo")

    assert code == int(ExitCode.BUSY)
    assert envelope["error"]["code"] == "STACK_BUSY"


def test_stack_down_is_refused_while_an_execution_occupies_the_stack(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("não podia montar a pilha")

    monkeypatch.setattr(stack_cmd, "build_stack_manager", refuse)
    plant(os.getpid(), command="probe")

    code, envelope = call(capsys, "stack", "down")

    assert code == int(ExitCode.BUSY)
    assert envelope["error"]["code"] == "STACK_BUSY"
