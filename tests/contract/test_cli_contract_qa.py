"""Testes independentes (QA) do contrato da CLI: envelope, códigos de saída, vazamentos."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import json
import subprocess
import sys
from pathlib import Path

import pytest
import typer

from harness_dast import __version__
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.output import Envelope, build_failure, build_success
from harness_dast.domain.errors import (
    CleanupError,
    ConfigError,
    ExitCode,
    ExternalToolError,
    HarnessError,
    PreflightError,
    ScopeViolation,
    StackBusy,
    TargetError,
)

pytestmark = pytest.mark.contract

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HDAST_LOG_LEVEL", "HDAST_ZAP_API_KEY", "HDAST_ZAP_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def app_raising(error: BaseException) -> typer.Typer:
    app = build_app()

    def boom() -> None:
        raise error

    app.command("boom")(boom)
    return app


# Tabela da especificação (seção 5 do documento de fundação).
SPEC_EXIT_CODES = {
    ConfigError: (2, "CONFIG_ERROR"),
    ScopeViolation: (3, "SCOPE_VIOLATION"),
    PreflightError: (4, "PREFLIGHT_FAILED"),
    ExternalToolError: (5, "EXTERNAL_TOOL_ERROR"),
}


@pytest.mark.parametrize("error_class", list(SPEC_EXIT_CODES))
@pytest.mark.parametrize("json_mode", [True, False])
def test_run_app_returns_spec_exit_code_when_each_error_class_is_raised(
    error_class: type[HarnessError], json_mode: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, error_code = SPEC_EXIT_CODES[error_class]
    args = (["--json"] if json_mode else []) + ["boom"]

    code = run_app(app_raising(error_class("falhou", hint="faça isto")), args)

    captured = capsys.readouterr()
    assert code == exit_code
    if json_mode:
        assert json.loads(captured.out)["error"]["code"] == error_code
        assert captured.err.strip() == "" or all(
            line.startswith("{") for line in captured.err.strip().splitlines()
        )
    else:
        assert captured.out == ""
        assert error_code in captured.err
        assert "faça isto" in captured.err


def test_exit_code_5_is_reserved_for_external_tool_failures_only() -> None:
    # O documento de fundação atribui 5 a "falha de ferramenta externa (ZAP, Docker)".
    # TargetError (o alvo respondeu mal) e CleanupError (SQL de limpeza) não são isso.
    assert TargetError.exit_code != ExitCode.EXTERNAL_TOOL
    assert CleanupError.exit_code != ExitCode.EXTERNAL_TOOL


def test_error_codes_are_unique_across_the_hierarchy() -> None:
    classes = [
        HarnessError,
        ConfigError,
        ScopeViolation,
        PreflightError,
        ExternalToolError,
        TargetError,
        CleanupError,
        StackBusy,
    ]

    codes = [c.code for c in classes]

    assert len(set(codes)) == len(codes)
    assert all(c == c.upper() and " " not in c for c in codes)


def test_exit_code_values_are_stable() -> None:
    assert {c.name: int(c) for c in ExitCode} == {
        "OK": 0,
        "FINDINGS": 1,
        "USAGE": 2,
        "SCOPE": 3,
        "PREFLIGHT": 4,
        "EXTERNAL_TOOL": 5,
        "TARGET": 6,
        "CLEANUP": 7,
        "BUSY": 8,
        "INTERNAL": 10,
        "INTERRUPTED": 130,
    }


def test_harness_error_exposes_message_and_hint_and_str() -> None:
    error = ConfigError("m", hint="h")

    assert (error.message, error.hint, str(error)) == ("m", "h", "m")
    assert ConfigError("m").hint is None


@pytest.mark.parametrize(
    "exception",
    [
        RuntimeError("detalhe-sensivel"),
        ValueError("x"),
        KeyError("k"),
        ZeroDivisionError(),
        OSError("disco"),
        UnicodeError("u"),
        AssertionError("a"),
        RecursionError(),
        MemoryError(),
        NotImplementedError(),
        ExceptionGroup("g", [ValueError("v")]),
    ],
)
def test_run_app_returns_internal_envelope_when_unexpected_exception_is_raised(
    exception: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(app_raising(exception), ["--json", "boom"])

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 10
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL"
    assert "Traceback" not in out
    assert out.count("\n") == 1


def test_run_app_never_leaks_secret_to_stdout_when_unexpected_exception_carries_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "SENHA-DO-ALVO-123"

    run_app(
        app_raising(RuntimeError(f"login falhou password={secret} token={JWT}")), ["--json", "boom"]
    )

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert JWT not in captured.out


def test_run_app_masks_jwt_in_stderr_log_when_unexpected_exception_carries_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_app(app_raising(RuntimeError(f"upstream devolveu {JWT}")), ["--json", "boom"])

    assert JWT not in capsys.readouterr().err


def test_run_app_masks_jwt_in_stderr_when_exception_is_chained_with_cause(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        try:
            raise ValueError(f"interno {JWT}")
        except ValueError as cause:
            raise RuntimeError("externo") from cause
    except RuntimeError as error:
        run_app(app_raising(error), ["boom"])

    assert JWT not in capsys.readouterr().err


def test_run_app_does_not_leak_traceback_to_stdout_in_text_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(app_raising(RuntimeError("x")), ["boom"])

    captured = capsys.readouterr()
    assert code == 10
    assert captured.out == ""
    assert "Traceback" not in captured.out


def test_run_app_returns_internal_when_harness_error_base_class_is_raised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_app(app_raising(HarnessError("base")), ["--json", "boom"]) == 10
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INTERNAL"


@pytest.mark.parametrize(
    "args",
    [
        ["comando-inexistente"],
        ["version", "--opcao-inexistente"],
        ["version", "extra"],
        ["--opcao-global-inexistente", "version"],
        ["--json", "comando-inexistente"],
        ["--json", "--json", "version", "x"],
        ["--json"],
    ],
)
def test_run_app_returns_usage_exit_code_when_arguments_are_wrong(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(build_app(), args)

    captured = capsys.readouterr()
    assert code == 2
    if "--json" in args:
        assert json.loads(captured.out)["error"]["code"] == "CONFIG_ERROR"
    else:
        assert captured.out == ""
        assert "CONFIG_ERROR" in captured.err


def test_run_app_prints_nothing_but_json_to_stdout_when_json_flag_is_after_the_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Decisão A-03: '--json' vale antes e depois do subcomando. (Este teste
    # exigia erro de uso, o comportamento defeituoso; agora exige o sucesso em JSON puro.)
    code = run_app(build_app(), ["version", "--json"])

    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["ok"] is True


def test_run_app_prints_help_and_exits_zero_when_no_command_given_in_human_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Decisão A-12: sem argumentos, a ajuda e saída 0 (antes: ajuda seguida de erro vazio).
    code = run_app(build_app(), [])

    captured = capsys.readouterr()
    assert code == 0
    assert "version" in captured.out
    assert captured.err == ""


def test_run_app_reports_config_error_with_message_when_no_command_given_in_json_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(build_app(), ["--json"])

    envelope = json.loads(capsys.readouterr().out)
    assert code == 2
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert envelope["error"]["message"].strip()


def test_help_does_not_emit_envelope_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_app(build_app(), ["--json", "--help"]) == 0
    assert '"schema_version"' not in capsys.readouterr().out


def test_version_command_help_exits_zero() -> None:
    assert run_app(build_app(), ["version", "--help"]) == 0


def test_run_app_is_reusable_across_invocations_without_state_leak(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = build_app()

    first = run_app(app, ["--json", "version"])
    capsys.readouterr()
    second = run_app(app, ["version"])

    assert (first, second) == (0, 0)
    assert capsys.readouterr().out == f"version: {__version__}\n"


def test_envelope_omits_absent_fields_and_orders_schema_version_first() -> None:
    success = build_success({"a": 1}, run_id="2026-11-12T21-04-11Z-agenda-7f3a")
    failure = build_failure(ConfigError("m"))

    assert list(json.loads(success.model_dump_json(exclude_none=True))) == [
        "schema_version",
        "ok",
        "run_id",
        "data",
    ]
    assert json.loads(failure.model_dump_json(exclude_none=True)) == {
        "schema_version": 1,
        "ok": False,
        "error": {"code": "CONFIG_ERROR", "message": "m"},
    }


def test_envelope_is_immutable() -> None:
    envelope = Envelope(ok=True, data={})

    with pytest.raises(ValueError):
        envelope.ok = False  # type: ignore[misc]  # prova da imutabilidade


def test_envelope_serializes_non_ascii_message_without_crashing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_app(app_raising(ConfigError("ação inválida — ç ã é 日本")), ["--json", "boom"])

    assert code == 2
    assert "ação" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_python_dash_m_runs_the_cli_and_exits_with_the_error_code(tmp_path: Path) -> None:
    # O diário de comandos grava na pasta de estado; o teste a isola e nunca toca a da máquina.
    env = {
        "PYTHONUTF8": "1",
        "SYSTEMROOT": r"C:\Windows",
        "PATH": "",
        "HDAST_STATE_DIR": str(tmp_path / "state"),
    }
    ok = subprocess.run(  # noqa: S603 - executável do próprio interpretador, argumentos fixos
        [sys.executable, "-m", "harness_dast", "--json", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        env=env,
    )
    bad = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "harness_dast", "--json", "nada"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        env=env,
    )

    assert ok.returncode == 0
    assert json.loads(ok.stdout)["data"] == {"version": __version__}
    assert ok.stderr == ""
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["error"]["code"] == "CONFIG_ERROR"
    assert "Traceback" not in bad.stderr


def test_python_dash_m_masks_nothing_and_prints_no_traceback_when_env_is_invalid() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "harness_dast", "--json", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        env={
            "PYTHONUTF8": "1",
            "SYSTEMROOT": "C:\\Windows",
            "PATH": "",
            "HDAST_LOG_LEVEL": "SEGREDO-X",
        },
    )

    assert result.returncode == 2
    assert "SEGREDO-X" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
