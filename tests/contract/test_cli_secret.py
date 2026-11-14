"""Contrato de `hdast secret`: envelope, recusa sem terminal e nenhum valor na saída (ADR 0030).

O cofre é SEMPRE um backend em memória: a trava global de `tests/conftest.py` faz qualquer teste
que tente o cofre real da máquina falhar.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.secrets import keyring_store
from harness_dast.adapters.secrets.keyring_store import KEYRING_SERVICE, backend_id
from harness_dast.cli import secrets_composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.cli.commands import secret as secret_command
from harness_dast.domain.errors import ExitCode
from tests.fakes.credential_store import MemoryBackend
from tests.fakes.profile_data import dump_yaml, valid_profile_data

pytestmark = pytest.mark.contract

VALUE = "SenhaDoCofre-Nao-Pode-Vazar-42"
NAME = "ACME_USER_A_SENHA"


class ScriptedPrompt:
    def __init__(self) -> None:
        self.confirm = True

    def read_value(self, name: str) -> str:
        return VALUE

    def confirm_removal(self, name: str) -> bool:
        return self.confirm


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> MemoryBackend:
    instance = MemoryBackend()
    monkeypatch.setattr(
        keyring_store, "ALLOWED_BACKENDS", keyring_store.ALLOWED_BACKENDS | {backend_id(instance)}
    )
    monkeypatch.setattr(secrets_composition, "default_backend", lambda: instance)
    monkeypatch.delenv("HDAST_PRODUCTS_DIR", raising=False)
    return instance


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> ScriptedPrompt:
    prompt = ScriptedPrompt()
    monkeypatch.setattr(secret_command, "_is_interactive", lambda: True)
    monkeypatch.setattr(secret_command, "TerminalSecretPrompt", lambda: prompt)
    return prompt


def write_product(tmp_path: Path) -> Path:
    data = valid_profile_data("demo")
    data["auth"]["accounts"][0]["password"] = {"secret_ref": f"keyring:{NAME}"}
    folder = tmp_path / "produtos" / "demo"
    folder.mkdir(parents=True)
    (folder / "target.yml").write_text(dump_yaml(data), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    return tmp_path / "produtos"


def run_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any], str]:
    code = run_app(build_app(), ["--json", *args])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_set_without_a_terminal_is_refused_with_config_error_and_writes_nothing(
    backend: MemoryBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, err = run_json(capsys, "secret", "set", NAME)

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "terminal interativo" in envelope["error"]["message"]
    assert backend.data == {}
    assert VALUE not in err


def test_delete_without_a_terminal_is_refused_and_keeps_the_value(
    backend: MemoryBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    backend.data[(KEYRING_SERVICE, NAME)] = VALUE

    code, envelope, _ = run_json(capsys, "secret", "delete", NAME)

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert backend.data == {(KEYRING_SERVICE, NAME): VALUE}


def test_a_value_on_the_command_line_is_not_an_option_of_set(
    backend: MemoryBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, _ = run_json(capsys, "secret", "set", NAME, "--value", VALUE)

    assert code == ExitCode.USAGE
    assert backend.data == {}
    assert VALUE not in json.dumps(envelope)


def test_set_in_a_terminal_stores_the_value_and_never_prints_it(
    backend: MemoryBackend, terminal: ScriptedPrompt, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, err = run_json(capsys, "secret", "set", NAME)

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    assert envelope["data"] == {"name": NAME, "replaced": False}
    assert backend.data == {(KEYRING_SERVICE, NAME): VALUE}
    assert VALUE not in json.dumps(envelope)
    assert VALUE not in err


def test_set_human_output_confirms_without_the_value(
    backend: MemoryBackend, terminal: ScriptedPrompt, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(build_app(), ["secret", "set", NAME])

    captured = capsys.readouterr()
    assert code == ExitCode.OK
    assert NAME in captured.out
    assert VALUE not in captured.out + captured.err


def test_invalid_name_is_a_config_error_even_in_a_terminal(
    backend: MemoryBackend, terminal: ScriptedPrompt, capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope, _ = run_json(capsys, "secret", "set", "HDAST_ZAP_KEY")

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert backend.data == {}


def test_delete_in_a_terminal_removes_after_confirmation(
    backend: MemoryBackend, terminal: ScriptedPrompt, capsys: pytest.CaptureFixture[str]
) -> None:
    backend.data[(KEYRING_SERVICE, NAME)] = VALUE

    code, envelope, _ = run_json(capsys, "secret", "delete", NAME)

    assert code == ExitCode.OK
    assert envelope["data"] == {"name": NAME, "removed": True, "existed": True}
    assert backend.data == {}


def test_delete_declined_keeps_the_value(
    backend: MemoryBackend, terminal: ScriptedPrompt, capsys: pytest.CaptureFixture[str]
) -> None:
    backend.data[(KEYRING_SERVICE, NAME)] = VALUE
    terminal.confirm = False

    code, envelope, _ = run_json(capsys, "secret", "delete", NAME)

    assert code == ExitCode.OK
    assert envelope["data"]["removed"] is False
    assert backend.data == {(KEYRING_SERVICE, NAME): VALUE}


def test_list_works_without_a_terminal_and_shows_names_and_presence_only(
    backend: MemoryBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = write_product(tmp_path)
    backend.data[(KEYRING_SERVICE, NAME)] = VALUE

    code, envelope, err = run_json(
        capsys, "secret", "list", "demo", "--products-dir", str(products)
    )

    assert code == ExitCode.OK
    assert envelope["data"]["product"] == "demo"
    assert envelope["data"]["entries"] == [
        {"name": NAME, "used_by": ["auth.accounts[user_a].password"], "present": True}
    ]
    assert VALUE not in json.dumps(envelope)
    assert VALUE not in err


def test_list_marks_a_missing_secret_in_the_human_output_with_the_command(
    backend: MemoryBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = write_product(tmp_path)

    code = run_app(build_app(), ["secret", "list", "demo", "--products-dir", str(products)])

    out = capsys.readouterr().out
    assert code == ExitCode.OK
    assert f"hdast secret set {NAME}" in out


def test_list_with_a_broken_vault_reports_secret_backend_error_with_a_hint(
    backend: MemoryBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = write_product(tmp_path)
    backend.error = OSError("cofre trancado")

    code, envelope, _ = run_json(capsys, "secret", "list", "demo", "--products-dir", str(products))

    assert code == ExitCode.PREFLIGHT
    assert envelope["error"]["code"] == "SECRET_BACKEND_ERROR"
    assert "env:NOME" in envelope["error"]["hint"]


def test_list_of_an_unknown_product_is_a_config_error(
    backend: MemoryBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    products = write_product(tmp_path)

    code, envelope, _ = run_json(
        capsys, "secret", "list", "nao-existe", "--products-dir", str(products)
    )

    assert code == ExitCode.USAGE
    assert envelope["error"]["code"] == "CONFIG_ERROR"


def test_unknown_backend_is_refused_not_silently_replaced(
    monkeypatch: pytest.MonkeyPatch,
    terminal: ScriptedPrompt,
    capsys: pytest.CaptureFixture[str],
) -> None:
    unlisted = MemoryBackend()  # fora da lista de cofres do sistema
    monkeypatch.setattr(secrets_composition, "default_backend", lambda: unlisted)

    code, envelope, _ = run_json(capsys, "secret", "set", NAME)

    assert code == ExitCode.PREFLIGHT
    assert envelope["error"]["code"] == "SECRET_BACKEND_ERROR"
    assert unlisted.data == {}
