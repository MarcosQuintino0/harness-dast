"""Contrato interativo da declaração humana."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from harness_dast.adapters.storage.human_confirmation_store import FileHumanConfirmationStore
from harness_dast.cli.app import build_app
from harness_dast.cli.commands import finding as finding_command
from harness_dast.cli.output import CliState
from harness_dast.domain.errors import ConfigError
from tests.fakes.human_confirmation import setup_case
from tests.fakes.human_report import RUN_ID


@pytest.mark.parametrize(
    ("json_mode", "interactive", "stdout_tty"),
    [(False, False, True), (False, True, False), (True, True, True)],
)
def test_cli_recusa_sem_terminal_ou_json(
    monkeypatch: pytest.MonkeyPatch, json_mode: bool, interactive: bool, stdout_tty: bool
) -> None:
    monkeypatch.setattr(finding_command, "is_interactive", lambda: interactive)
    monkeypatch.setattr(
        finding_command, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: stdout_tty))
    )
    result = CliRunner().invoke(
        build_app(),
        ["finding", "acknowledge", "vampi", "--run", RUN_ID, "f" * 64],
        obj=CliState(json_mode=json_mode),
    )
    assert isinstance(result.exception, ConfigError)
    assert "terminal interativo" in str(result.exception)


def test_comando_interativo_registra_declaracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fingerprint = setup_case(tmp_path, None)
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(finding_command, "is_interactive", lambda: True)
    monkeypatch.setattr(
        finding_command, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True))
    )
    result = CliRunner().invoke(
        build_app(),
        ["finding", "acknowledge", "vampi", "--run", RUN_ID, fingerprint],
        input=f"Ana\nvi a resposta\n{fingerprint}\n",
        obj=CliState(),
    )
    assert result.exit_code == 0, result.exception
    assert "Confirmação registrada." in result.stdout
    assert "Quem confirmou" in result.stderr
    assert "O que você viu" in result.stderr
    saved = FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID)
    assert saved is not None
    assert saved.entries[0].observation == "vi a resposta"


def test_comando_cancela_quando_fingerprint_nao_e_confirmado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fingerprint = setup_case(tmp_path, None)
    monkeypatch.setenv("HDAST_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(finding_command, "is_interactive", lambda: True)
    monkeypatch.setattr(
        finding_command, "sys", SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True))
    )
    result = CliRunner().invoke(
        build_app(),
        ["finding", "acknowledge", "vampi", "--run", RUN_ID, fingerprint],
        input="Ana\nvi a resposta\ncancelar\n",
        obj=CliState(),
    )
    assert result.exit_code == 0, result.exception
    assert "Confirmação cancelada" in result.stdout
    assert FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID) is None
