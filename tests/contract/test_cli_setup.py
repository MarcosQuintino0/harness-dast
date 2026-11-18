"""Contrato de `hdast setup`: só a pessoa, em terminal; senhas e aprovação em ordem (ADR 0114).

O cofre é SEMPRE um backend em memória e o terminal é simulado: nenhum teste abre rede, usa o
cofre real nem aprova por conta própria.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.core import TyperCommand, TyperGroup
from typer.main import get_command

from harness_dast.adapters.secrets import keyring_store
from harness_dast.adapters.secrets.keyring_store import KEYRING_SERVICE, backend_id
from harness_dast.cli import secrets_composition
from harness_dast.cli.app import START_HERE_PANEL, build_app, run_app
from harness_dast.cli.approval_prompt import PAUSE_TEXT, TerminalApprovalPrompt
from harness_dast.cli.commands import setup as setup_command
from harness_dast.domain.errors import ExitCode
from tests.fakes.credential_store import MemoryBackend
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

VALUE = "SenhaDoCofre-Nao-Pode-Vazar-42"
NAME = "ACME_USER_A_SENHA"
NOTE = "# Padrão mínimo da CLI: limits.requests_per_second = 1 (resposta 'não sei' na carta)\n"


class ScriptedSecretPrompt:
    def read_value(self, name: str) -> str:
        return VALUE

    def confirm_removal(self, name: str) -> bool:
        return False


class ScriptedApproval:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.shown: list[tuple[str, ...]] = []

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        self.shown.append(summary)
        return self.answer


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> MemoryBackend:
    instance = MemoryBackend()
    monkeypatch.setattr(
        keyring_store, "ALLOWED_BACKENDS", keyring_store.ALLOWED_BACKENDS | {backend_id(instance)}
    )
    monkeypatch.setattr(secrets_composition, "default_backend", lambda: instance)
    monkeypatch.delenv("HDAST_PRODUCTS_DIR", raising=False)
    return instance


def write_product(tmp_path: Path, *, note: str = "") -> Path:
    data = valid_profile_data("demo")
    data["auth"]["accounts"][0]["password"] = {"secret_ref": f"keyring:{NAME}"}
    folder = tmp_path / "produtos" / "demo"
    folder.mkdir(parents=True)
    (folder / "target.yml").write_text(note + dump_yaml(data), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    return tmp_path / "produtos"


def terminal(monkeypatch: pytest.MonkeyPatch, *, answer: bool) -> ScriptedApproval:
    approval = ScriptedApproval(answer)
    monkeypatch.setattr(setup_command, "_is_interactive", lambda: True)
    monkeypatch.setattr(setup_command, "TerminalSecretPrompt", ScriptedSecretPrompt)
    monkeypatch.setattr(setup_command, "TerminalApprovalPrompt", lambda *, pause: approval)
    return approval


def run(
    capsys: pytest.CaptureFixture[str], products: Path, *, json_mode: bool
) -> tuple[int, dict[str, Any], str, str]:
    args = (["--json"] if json_mode else []) + ["setup", "demo", "--products-dir", str(products)]
    code = run_app(build_app(), args)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out) if json_mode and captured.out.strip() else {}
    return code, parsed, captured.out, captured.err


def approval_file(tmp_path: Path) -> Path:
    return tmp_path / "isolated-hdast-state" / "approvals" / "demo.json"


def test_setup_without_a_terminal_is_refused_and_writes_nothing(
    tmp_path: Path, backend: MemoryBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    products = write_product(tmp_path)

    code, envelope, _, _ = run(capsys, products, json_mode=True)

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "Só uma pessoa" in envelope["error"]["message"]
    assert backend.data == {}
    assert not approval_file(tmp_path).exists()


def test_setup_with_json_is_refused_even_in_a_real_terminal(
    tmp_path: Path,
    backend: MemoryBackend,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = terminal(monkeypatch, answer=True)
    products = write_product(tmp_path)

    code, envelope, _, _ = run(capsys, products, json_mode=True)

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert approval.shown == []
    assert backend.data == {}
    assert not approval_file(tmp_path).exists()


def test_setup_writes_the_missing_password_and_approves_without_leaking_the_value(
    tmp_path: Path,
    backend: MemoryBackend,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = terminal(monkeypatch, answer=True)
    products = write_product(tmp_path, note=NOTE)

    code, _, out, err = run(capsys, products, json_mode=False)

    assert code == ExitCode.OK
    assert backend.data == {(KEYRING_SERVICE, NAME): VALUE}
    assert "APROVADO" in out
    assert NAME in out
    assert VALUE not in out + err
    assert approval.shown[0][0].startswith("PADRÃO MÍNIMO DA CLI")
    assert "  - limits.requests_per_second = 1" in approval.shown[0]
    assert json.loads(approval_file(tmp_path).read_text(encoding="utf-8"))["product"] == "demo"


def test_setup_without_the_person_confirming_keeps_the_password_but_does_not_approve(
    tmp_path: Path,
    backend: MemoryBackend,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal(monkeypatch, answer=False)
    products = write_product(tmp_path)

    code, _, out, _ = run(capsys, products, json_mode=False)

    assert code == ExitCode.OK
    assert "nenhuma aprovação foi gravada" in out
    assert "nada foi gravado" not in out
    assert "continuam no cofre" in out
    assert (KEYRING_SERVICE, NAME) in backend.data
    assert not approval_file(tmp_path).exists()


def test_setup_stops_with_a_usage_error_on_a_profile_that_is_not_ready(
    tmp_path: Path,
    backend: MemoryBackend,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = terminal(monkeypatch, answer=True)
    products = write_product(tmp_path)
    (products / "demo" / "openapi.json").unlink()

    code, _, _, err = run(capsys, products, json_mode=False)

    assert code == ExitCode.USAGE
    assert "FILE_MISSING" in err
    assert backend.data == {}
    assert approval.shown == []


def test_setup_is_registered_in_the_start_here_panel() -> None:
    root = get_command(build_app())
    assert isinstance(root, TyperGroup)

    command = root.commands["setup"]
    assert isinstance(command, TyperCommand)
    assert command.rich_help_panel == START_HERE_PANEL


# ------------------------------------------------------------- prompt com pausa


def feed(monkeypatch: pytest.MonkeyPatch, answers: list[object]) -> list[str]:
    asked: list[str] = []
    queue = iter(answers)

    def fake_prompt(text: str, *args: object, **kwargs: object) -> str:
        asked.append(text)
        item = next(queue)
        if isinstance(item, BaseException):
            raise item
        return str(item)

    monkeypatch.setattr(typer, "prompt", fake_prompt)
    return asked


def test_prompt_with_pause_shows_the_pause_text_then_asks_the_product_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = feed(monkeypatch, ["", "demo"])

    result = TerminalApprovalPrompt(pause=True).confirm("demo", ("Produto: demo",), ())

    assert result is True
    assert PAUSE_TEXT in capsys.readouterr().err
    assert len(asked) == 2
    assert "Digite 'demo'" in asked[1]


def test_prompt_with_pause_does_not_approve_when_ctrl_c_hits_the_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = feed(monkeypatch, [typer.Abort()])

    result = TerminalApprovalPrompt(pause=True).confirm("demo", ("Produto: demo",), ())

    assert result is False
    assert len(asked) == 1


@pytest.mark.parametrize("typed", ["", "DEMO", "outro", "dem"])
def test_prompt_with_pause_does_not_approve_when_the_name_is_wrong(
    monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    feed(monkeypatch, ["", typed])

    assert TerminalApprovalPrompt(pause=True).confirm("demo", ("Produto: demo",), ()) is False


def test_prompt_without_pause_asks_only_for_the_product_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = feed(monkeypatch, ["demo"])

    assert TerminalApprovalPrompt().confirm("demo", ("Produto: demo",), ()) is True
    assert PAUSE_TEXT not in capsys.readouterr().err
    assert len(asked) == 1
