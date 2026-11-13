import json

import pytest

from harness_dast.cli.output import (
    SCHEMA_VERSION,
    CliState,
    Envelope,
    build_failure,
    build_success,
    emit,
)
from harness_dast.domain.errors import ScopeViolation


def test_success_envelope_has_schema_version_and_data_when_built() -> None:
    envelope = build_success({"version": "1"}, run_id="r1")

    assert envelope.schema_version == SCHEMA_VERSION == 1
    assert envelope.ok is True
    assert envelope.run_id == "r1"
    assert envelope.data == {"version": "1"}
    assert envelope.error is None


def test_failure_envelope_carries_error_fields_when_built_from_harness_error() -> None:
    envelope = build_failure(ScopeViolation("fora do escopo", hint="peça ao dono"))

    assert envelope.ok is False
    assert envelope.error is not None
    assert (envelope.error.code, envelope.error.message, envelope.error.hint) == (
        "SCOPE_VIOLATION",
        "fora do escopo",
        "peça ao dono",
    )


def test_envelope_is_frozen_when_modification_is_attempted() -> None:
    envelope = build_success({})

    with pytest.raises(ValueError, match="frozen"):
        envelope.ok = False  # type: ignore[misc]  # prova que o modelo é congelado


def test_json_omits_absent_fields_when_serialized(capsys: pytest.CaptureFixture[str]) -> None:
    emit(build_success({"a": 1}), json_mode=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"schema_version": 1, "ok": True, "data": {"a": 1}}


def test_failure_goes_to_stdout_as_json_when_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    emit(build_failure(ScopeViolation("x")), json_mode=True)

    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"] == {"code": "SCOPE_VIOLATION", "message": "x"}
    assert captured.err == ""


def test_human_success_goes_to_stdout_when_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    emit(build_success({"version": "0.1.0"}), json_mode=False)

    captured = capsys.readouterr()
    assert captured.out == "version: 0.1.0\n"
    assert captured.err == ""


def test_human_failure_goes_to_stderr_with_hint_when_not_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    emit(build_failure(ScopeViolation("fora", hint="faça isto")), json_mode=False)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Erro [SCOPE_VIOLATION]: fora" in captured.err
    assert "faça isto" in captured.err


def test_envelope_without_error_renders_empty_when_failure_lacks_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    emit(Envelope(ok=False), json_mode=False)

    assert capsys.readouterr().out == ""


def test_cli_state_defaults_to_human_mode_when_created() -> None:
    assert CliState().json_mode is False
