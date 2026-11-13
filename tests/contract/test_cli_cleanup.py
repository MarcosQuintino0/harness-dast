"""Contrato de `hdast cleanup`: envelope, códigos de saída e o token fora do JSON.

O arquivo de perfil, o script, o manifesto e a pasta de execuções são REAIS (em `tmp_path`); só o
banco é um falso, injetado no lugar do executor Oracle na montagem da CLI.
"""

import io
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.cli import composition
from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.cleanup_ports import FakeDatabase, FakeExecutor, finished_manifest
from tests.fakes.cleanup_rig import FINISHED, RUN_ID, SCRIPT, SECRETS, STARTED, cleanup_profile
from tests.fakes.profile_data import valid_profile_data

pytestmark = pytest.mark.contract

TOKEN_PATTERN = re.compile(r"hdc-[A-Za-z0-9_-]{20,}")
SECRET_VALUES = [v for k, v in SECRETS.items() if k != "ACME_USER_A_SENHA"]


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> FakeDatabase:
    db = FakeDatabase({"PEDIDO": 10, "ITEM": 20}, {1: 3, 2: 2})
    monkeypatch.setattr(composition, "OracleCleanupExecutor", lambda: FakeExecutor(db))
    return db


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in ("HDAST_PRODUCTS_DIR", "HDAST_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    runs = tmp_path / "runs"
    monkeypatch.setenv("HDAST_RUNS_DIR", str(runs))
    write_product(tmp_path / "produtos")
    write_run(runs)
    return tmp_path


def write_product(products: Path, script: str = SCRIPT, **profile_changes: Any) -> None:
    folder = products / "demo"
    (folder / "cleanup").mkdir(parents=True, exist_ok=True)
    profile = cleanup_profile(**profile_changes)
    data = json.loads(profile.model_dump_json())
    data["scope"]["windows"] = [valid_profile_data()["scope"]["windows"][0]]
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.json").write_text("{}", encoding="utf-8")
    (folder / "cleanup" / "cleanup.sql").write_text(script, encoding="utf-8")


def write_run(runs: Path) -> None:
    folder = runs / RUN_ID
    folder.mkdir(parents=True, exist_ok=True)
    manifest = finished_manifest(RUN_ID, "demo", STARTED, finished_at=FINISHED)
    (folder / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")


def cleanup_args(workspace: Path, *extra: str) -> list[str]:
    return [
        "cleanup",
        "demo",
        "--run",
        RUN_ID,
        "--products-dir",
        str(workspace / "produtos"),
        *extra,
    ]


def invoke(
    capsys: pytest.CaptureFixture[str], workspace: Path, *extra: str, json_mode: bool = True
) -> tuple[int, str, str]:
    args = cleanup_args(workspace, *extra)
    code = run_app(build_app(), ["--json", *args] if json_mode else args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def token_from(err: str) -> str:
    match = TOKEN_PATTERN.search(err)
    assert match, "o token deveria aparecer no stderr do --dry-run"
    return match.group(0)


def assert_no_secrets(*texts: str) -> None:
    for text in texts:
        for secret in SECRET_VALUES:
            assert secret not in text


def test_dry_run_returns_the_envelope_and_prints_the_token_only_on_stderr(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    code, out, err = invoke(capsys, workspace, "--dry-run")

    assert code == ExitCode.OK
    envelope = json.loads(out)
    assert set(envelope) == {"schema_version", "ok", "run_id", "data"}
    assert (envelope["ok"], envelope["run_id"]) == (True, RUN_ID)
    data = envelope["data"]
    assert data["status"] == "dry_run"
    assert (data["committed"], data["rolled_back"]) == (False, True)
    assert data["total_rows"] == 5
    assert [(s["index"], s["table"], s["rows"]) for s in data["statements"]] == [
        (1, "ITEM", 3),
        (2, "PEDIDO", 2),
    ]
    token = token_from(err)
    assert token not in out
    assert "confirmation_token" not in out
    assert "token" not in set(data)
    assert database.commits == 0
    assert_no_secrets(out, err)


def test_cleanup_json_and_audit_are_written_without_token_or_secrets(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    _, _, err = invoke(capsys, workspace, "--dry-run")

    folder = workspace / "runs" / RUN_ID
    record = (folder / "cleanup.json").read_text(encoding="utf-8")
    audit = (folder / "cleanup-audit.jsonl").read_text(encoding="utf-8")
    confirmation = (folder / "cleanup-confirmation.json").read_text(encoding="utf-8")
    assert json.loads(record)["status"] == "dry_run"
    assert [json.loads(line)["event"] for line in audit.splitlines()] == ["started", "finished"]
    for text in (record, audit, confirmation):
        assert token_from(err) not in text
        assert_no_secrets(text)


def test_confirm_with_the_token_commits_once_and_the_token_dies(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    _, _, err = invoke(capsys, workspace, "--dry-run")
    token = token_from(err)

    code, out, _ = invoke(capsys, workspace, "--confirm", token)
    again, again_out, _ = invoke(capsys, workspace, "--confirm", token)

    assert code == ExitCode.OK
    data = json.loads(out)["data"]
    assert (data["status"], data["committed"], data["confirmation_method"]) == (
        "committed",
        True,
        "token",
    )
    assert token not in out
    assert database.commits == 1
    assert (again, json.loads(again_out)["error"]["code"]) == (ExitCode.USAGE, "CONFIG_ERROR")
    assert database.commits == 1


def test_without_terminal_and_without_token_it_refuses_with_usage_error_and_no_connection(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    code, out, _ = invoke(capsys, workspace)

    envelope = json.loads(out)
    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert "--dry-run" in envelope["error"]["hint"]
    assert database.opened == []


def interactive(monkeypatch: pytest.MonkeyPatch, typed: str) -> None:
    monkeypatch.setattr("harness_dast.cli.commands.cleanup._is_interactive", lambda: True)
    monkeypatch.setattr("sys.stdin", io.StringIO(typed))


def test_interactive_person_typing_the_product_name_commits(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    database: FakeDatabase,
) -> None:
    interactive(monkeypatch, "demo\n")

    code, out, err = invoke(capsys, workspace)

    assert code == ExitCode.OK
    assert json.loads(out)["data"]["status"] == "committed"
    assert json.loads(out)["data"]["confirmation_method"] == "interactive"
    assert "APAGADAS DE VERDADE" in err
    assert "ITEM -> 3 linha(s)" in err
    assert database.commits == 1


@pytest.mark.parametrize("typed", ["outro\n", "\n", "DEMO\n", " \n"])
def test_interactive_person_typing_anything_else_declines_and_nothing_is_committed(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    database: FakeDatabase,
    typed: str,
) -> None:
    interactive(monkeypatch, typed)

    code, out, _ = invoke(capsys, workspace)

    assert code == ExitCode.OK
    data = json.loads(out)["data"]
    assert (data["status"], data["committed"], data["rolled_back"]) == ("declined", False, True)
    assert database.commits == 0


def test_statement_failure_exits_7_names_index_and_table_and_leaks_nothing(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    database.fail_at = 2

    code, out, err = invoke(capsys, workspace, "--dry-run")

    envelope = json.loads(out)
    assert code == ExitCode.CLEANUP
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CLEANUP_FAILED"
    assert "comando 2" in envelope["error"]["message"]
    assert "PEDIDO" in envelope["error"]["message"]
    assert database.commits == 0
    assert not TOKEN_PATTERN.search(out + err)
    assert_no_secrets(out, err)


def test_row_ceiling_exceeded_exits_7(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    write_product(workspace / "produtos", max_rows=4)

    code, out, _ = invoke(capsys, workspace, "--dry-run")

    assert code == ExitCode.CLEANUP
    assert "acima do teto de 4" in json.loads(out)["error"]["message"]
    assert database.commits == 0


def test_rejected_script_exits_2_before_any_connection(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    write_product(workspace / "produtos", script="DELETE FROM PEDIDO;\nDROP TABLE ITEM;")

    code, out, _ = invoke(capsys, workspace, "--dry-run")

    assert code == ExitCode.USAGE
    assert json.loads(out)["error"]["code"] == "CONFIG_ERROR"
    assert database.opened == []


def test_unknown_run_exits_2(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    code = run_app(
        build_app(),
        [
            "--json",
            "cleanup",
            "demo",
            "--run",
            "2020-01-01T00-00-00Z-demo-aaaa",
            "--dry-run",
            "--products-dir",
            str(workspace / "produtos"),
        ],
    )

    assert code == ExitCode.USAGE
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "CONFIG_ERROR"
    assert database.opened == []


def test_expired_authorization_exits_3(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    write_product(workspace / "produtos", valid_until="2020-01-01")

    code, out, _ = invoke(capsys, workspace, "--dry-run")

    assert code == ExitCode.SCOPE
    assert json.loads(out)["error"]["code"] == "SCOPE_VIOLATION"
    assert database.opened == []


def test_human_mode_shows_plan_on_stdout_and_token_on_stderr(
    capsys: pytest.CaptureFixture[str], workspace: Path, database: FakeDatabase
) -> None:
    code, out, err = invoke(capsys, workspace, "--dry-run", json_mode=False)

    assert code == ExitCode.OK
    assert "SIMULAÇÃO" in out
    assert "Total: 5 linha(s)" in out
    assert "Script SHA-256:" in out
    token = token_from(err)
    assert token not in out
    assert "--confirm <token>" in err


def test_help_lists_the_command_and_its_flags(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_app(build_app(), ["cleanup", "--help"])
    out = capsys.readouterr().out

    assert code == ExitCode.OK
    for flag in ("--run", "--dry-run", "--confirm", "--products-dir"):
        assert flag in out
