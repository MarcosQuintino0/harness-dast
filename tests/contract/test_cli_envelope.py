"""Contrato público da CLI: envelope JSON e códigos de saída, pela CLI real."""

import json
import sys
from pathlib import Path

import pytest
import typer

from harness_dast import __version__
from harness_dast.__main__ import main
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import (
    CleanupError,
    ConfigError,
    ExternalToolError,
    HarnessError,
    PreflightError,
    ScopeViolation,
    StackBusy,
    TargetError,
)

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HDAST_LOG_LEVEL", raising=False)


def _app_with_failing_command(raiser: BaseException) -> typer.Typer:
    app = build_app()

    def boom() -> None:
        raise raiser

    app.command("boom")(boom)
    return app


def test_version_returns_success_envelope_when_json_flag_is_used(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(build_app(), ["--json", "version"])

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": 1,
        "ok": True,
        "data": {"version": __version__},
    }


def test_version_prints_plain_text_when_json_flag_is_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(build_app(), ["version"])

    assert code == 0
    assert capsys.readouterr().out == f"version: {__version__}\n"


def test_version_flag_prints_the_version_without_creating_state(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("HDAST_STATE_DIR", str(state))
    monkeypatch.setattr(sys, "argv", ["hdast", "--version"])

    code = main()

    assert code == 0
    assert capsys.readouterr().out == f"{__version__}\n"
    assert not state.exists()


@pytest.mark.parametrize(
    ("error", "exit_code", "error_code"),
    [
        (ConfigError("c", hint="h"), 2, "CONFIG_ERROR"),
        (ScopeViolation("s", hint="h"), 3, "SCOPE_VIOLATION"),
        (PreflightError("p", hint="h"), 4, "PREFLIGHT_FAILED"),
        (ExternalToolError("e", hint="h"), 5, "EXTERNAL_TOOL_ERROR"),
    ],
)
def test_harness_error_becomes_failure_envelope_and_exit_code_when_raised(
    capsys: pytest.CaptureFixture[str], error: HarnessError, exit_code: int, error_code: str
) -> None:
    code = run_app(_app_with_failing_command(error), ["--json", "boom"])

    assert code == exit_code
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": 1,
        "ok": False,
        "error": {"code": error_code, "message": error.message, "hint": "h"},
    }


def test_unexpected_exception_becomes_internal_error_without_traceback_when_raised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(_app_with_failing_command(RuntimeError("detalhe-sensivel")), ["--json", "boom"])

    captured = capsys.readouterr()
    assert code == 10
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL"
    assert "Traceback" not in captured.out
    assert "detalhe-sensivel" not in captured.out


def test_usage_error_becomes_config_envelope_when_command_is_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(build_app(), ["--json", "comando-inexistente"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "CONFIG_ERROR"


def test_invalid_environment_becomes_config_envelope_when_log_level_is_wrong(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HDAST_LOG_LEVEL", "NADA")

    code = run_app(build_app(), ["--json", "version"])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "CONFIG_ERROR"


def test_help_exits_zero_when_requested() -> None:
    assert run_app(build_app(), ["--help"]) == 0


@pytest.mark.parametrize("raiser", [KeyboardInterrupt(), typer.Abort()])
def test_run_app_exits_130_with_interrupted_envelope_when_user_interrupts(
    raiser: BaseException, capsys: pytest.CaptureFixture[str]
) -> None:
    app = build_app()

    def boom() -> None:
        raise raiser

    app.command("boom")(boom)

    code = run_app(app, ["boom", "--json"])

    captured = capsys.readouterr()
    assert code == 130
    assert json.loads(captured.out)["error"]["code"] == "INTERRUPTED"
    assert "Traceback" not in captured.out + captured.err


def test_run_app_prints_short_message_on_stderr_when_user_interrupts_in_human_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(_app_with_failing_command(KeyboardInterrupt()), ["boom"])

    captured = capsys.readouterr()
    assert code == 130
    assert captured.out == ""
    assert "INTERRUPTED" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [(TargetError("x"), 6), (CleanupError("x"), 7), (StackBusy("x"), 8)],
)
def test_run_app_maps_target_and_cleanup_errors_to_their_own_exit_codes(
    error: HarnessError, exit_code: int
) -> None:
    assert run_app(_app_with_failing_command(error), ["boom"]) == exit_code


@pytest.mark.parametrize("argv", [["--json", "naoexiste"], ["naoexiste", "--json"]])
def test_run_app_prints_only_json_to_stdout_when_json_flag_and_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(build_app(), argv)

    captured = capsys.readouterr()
    assert code == 2
    assert json.loads(captured.out)["error"]["code"] == "CONFIG_ERROR"


def test_run_app_keeps_json_flag_after_double_dash_untouched() -> None:
    from harness_dast.cli.app import _extract_json_flag

    assert _extract_json_flag(["a", "--", "--json"]) == (["a", "--", "--json"], False)
