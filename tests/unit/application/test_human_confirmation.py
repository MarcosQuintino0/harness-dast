"""Contratos da declaração humana sem rede nem terminal real."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.human_confirmation_store import FileHumanConfirmationStore
from harness_dast.application.human_confirmation import AcknowledgeFinding
from harness_dast.cli.app import build_app
from harness_dast.cli.commands import finding as finding_command
from harness_dast.cli.output import CliState
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding_confidence import confidence_step
from tests.unit.domain.panel.helpers import findings_report
from tests.unit.domain.report.helpers import RUN_ID


class Clock:
    def now(self) -> datetime:
        return datetime(2026, 11, 16, tzinfo=UTC)


class Prompt:
    def __init__(self, answer: tuple[str, str] | None) -> None:
        self.answer = answer

    def ask(self, fingerprint: str) -> tuple[str, str] | None:
        return self.answer


def setup_case(tmp_path: Path, answer: tuple[str, str] | None) -> tuple[AcknowledgeFinding, str]:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    report = findings_report()
    (folder / "findings.json").write_text(report.model_dump_json(), encoding="utf-8")
    case = AcknowledgeFinding(
        FileHumanConfirmationStore(tmp_path),
        FileRunArtifacts(tmp_path),
        Prompt(answer),
        Clock(),
        lambda text: text.replace("senha-conhecida", "***"),
    )
    return case, report.findings[0].fingerprint


def test_registra_sem_perder_anterior_e_redige_observacao(tmp_path: Path) -> None:
    case, fingerprint = setup_case(tmp_path, ("Ana", "token=abc123 senha-conhecida"))
    original = (tmp_path / RUN_ID / "findings.json").read_bytes()
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    result = FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID)
    assert result is not None
    assert len(result.entries) == 2
    assert result.entries[0].observation == "token=*** ***"
    assert (
        confidence_step(
            findings_report().findings[0], confirmed_by_person=result.contains(fingerprint)
        )
        == "confirmada"
    )
    assert (tmp_path / RUN_ID / "findings.json").read_bytes() == original


def test_nao_grava_quando_cancelado(tmp_path: Path) -> None:
    case, fingerprint = setup_case(tmp_path, None)
    assert not case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID) is None


@pytest.mark.parametrize("answer", [("", "vi"), ("Ana", "  "), (" ", "vi")])
def test_recusa_declaracao_ausente(tmp_path: Path, answer: tuple[str, str]) -> None:
    case, fingerprint = setup_case(tmp_path, answer)
    with pytest.raises(ConfigError):
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID) is None


@pytest.mark.parametrize(
    ("product", "run_id", "fingerprint", "interactive"),
    [
        ("vampi", RUN_ID, "f" * 64, True),
        ("outro", RUN_ID, "f" * 64, True),
        ("vampi", "../invalido", "f" * 64, True),
        ("vampi", RUN_ID, "f" * 64, False),
    ],
)
def test_recusa_contexto_ou_terminal_invalido(
    tmp_path: Path, product: str, run_id: str, fingerprint: str, interactive: bool
) -> None:
    case, _ = setup_case(tmp_path, ("Ana", "vi"))
    with pytest.raises(ConfigError):
        case.execute(product, run_id, fingerprint, interactive=interactive)
    assert not (tmp_path / RUN_ID / "human-confirmations.json").exists()


@pytest.mark.parametrize(
    "contents",
    [
        "{",
        "{}",
        "null",
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":true,"product":"vampi","run_id":"' + RUN_ID + '","entries":[]}',
        '{"schema_version":2}',
        '{"schema_version":1,"product":"outro","run_id":"' + RUN_ID + '","entries":[]}',
    ],
)
def test_recusa_arquivo_malformado_sem_apagar(tmp_path: Path, contents: str) -> None:
    case, fingerprint = setup_case(tmp_path, ("Ana", "vi"))
    path = tmp_path / RUN_ID / "human-confirmations.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert contents not in str(error.value)
    assert path.read_text(encoding="utf-8") == contents


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
    saved = FileHumanConfirmationStore(tmp_path).read("vampi", RUN_ID)
    assert saved is not None
    assert saved.entries[0].observation == "vi a resposta"


def test_trava_concorrente_preserva_registros(tmp_path: Path) -> None:
    case, fingerprint = setup_case(tmp_path, ("Ana", "vi"))
    assert case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    folder = tmp_path / RUN_ID
    before = (folder / "human-confirmations.json").read_bytes()
    (folder / ".human-confirmations.lock").touch()
    with pytest.raises(ConfigError):
        case.execute("vampi", RUN_ID, fingerprint, interactive=True)
    assert (folder / "human-confirmations.json").read_bytes() == before
