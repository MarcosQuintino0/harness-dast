"""Contrato de `hdast panel`: envelope JSON, códigos de saída, páginas gravadas e erros de uso."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness_dast.cli.app import build_app, run_app
from harness_dast.domain.errors import ExitCode
from tests.fakes.profile_data import valid_profile_data
from tests.unit.domain.panel_helpers import findings_report, run_summary
from tests.unit.domain.report_helpers import RUN_ID, entry, operation, probe_result, scan_result

pytestmark = pytest.mark.contract

OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "Vampi", "version": "1"},
    "paths": {
        "/users/v1/{username}": {
            "get": {
                "operationId": "obter",
                "summary": "Ver usuário",
                "tags": ["Usuários"],
                "parameters": [
                    {
                        "name": "username",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    },
}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    runs, products = tmp_path / "runs", tmp_path / "produtos"
    folder = products / "vampi"
    folder.mkdir(parents=True)
    data = valid_profile_data("vampi")
    (folder / "target.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (folder / "openapi.json").write_text(json.dumps(OPENAPI), encoding="utf-8")
    monkeypatch.setenv("HDAST_RUNS_DIR", str(runs))
    monkeypatch.setenv("HDAST_PRODUCTS_DIR", str(products))
    return runs, products


def write_run(runs: Path, run_id: str = RUN_ID, *, product: str = "vampi") -> Path:
    folder = runs / run_id
    folder.mkdir(parents=True)
    probe = probe_result([operation("obter", "GET", "/users/v1/{username}")], run_id=run_id)
    scan = scan_result([entry("obter", "GET", "/users/v1/{username}", 4)], run_id=run_id)
    (folder / "probe.json").write_text(
        probe.model_copy(update={"product": product}).model_dump_json(), encoding="utf-8"
    )
    (folder / "scan.json").write_text(
        scan.model_copy(update={"product": product}).model_dump_json(), encoding="utf-8"
    )
    (folder / "findings.json").write_text(findings_report().model_dump_json(), encoding="utf-8")
    (folder / "run.json").write_text(
        run_summary(run_id=run_id, product=product).model_dump_json(), encoding="utf-8"
    )
    return folder


def invoke(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = run_app(build_app(), list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def invoke_json(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict[str, Any]]:
    code, out, _ = invoke(capsys, "--json", *args)
    return code, json.loads(out)


def test_panel_writes_the_six_pages_and_answers_with_the_envelope(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert envelope["ok"] is True
    assert envelope["schema_version"] == 1
    assert envelope["run_id"] == RUN_ID
    data = envelope["data"]
    assert data["product"] == "vampi"
    assert data["directory"] == "panel"
    assert data["entry"] == "panel/summary.html"
    assert len(data["files"]) == 6
    assert data["verdict"] == "finished"
    assert data["severe_findings"] == 1
    assert data["sources"] == ["run.json", "probe.json", "scan.json", "findings.json"]
    assert "metrics.json" in data["missing"]
    for name in data["files"]:
        assert (folder / name).is_file()
    page = (folder / "panel" / "summary.html").read_text(encoding="utf-8")
    assert "Ver usuário" in page
    assert "<script" not in page


def test_panel_without_run_uses_the_latest_execution_of_the_product(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    write_run(runs, "2026-11-12T05-15-32Z-vampi-cd34")
    write_run(runs)

    code, envelope = invoke_json(capsys, "panel", "vampi")

    assert code == ExitCode.OK
    assert envelope["run_id"] == RUN_ID


def test_panel_human_output_says_where_the_pages_are_and_what_is_missing(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    write_run(runs)

    code, out, err = invoke(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert f"Painel de vampi, execução {RUN_ID}: terminou, 1 falha(s) grave(s)." in out
    assert "panel/summary.html" in out
    assert (
        "Não encontrados (aparecem como 'não medido'): manifest.json, authz.json, metrics.json"
        in out
    )
    assert err == ""


def test_panel_is_regenerated_in_place_without_leftovers(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    invoke(capsys, "panel", "vampi", "--run", RUN_ID)
    code, _ = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert sorted(item.name for item in (folder / "panel").iterdir()) == sorted(
        [
            "summary.html",
            "stages.html",
            "findings.html",
            "coverage.html",
            "terminal.html",
            "time-and-tokens.html",
        ]
    )


def test_panel_for_a_missing_run_is_a_usage_error(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "CONFIG_ERROR"
    assert envelope["error"]["hint"]


def test_panel_for_a_product_with_no_execution_says_what_to_do(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = invoke_json(capsys, "panel", "vampi")

    assert code == ExitCode.USAGE
    assert "nenhuma execução" in envelope["error"]["message"]


def test_panel_for_a_run_of_another_product_is_refused_and_writes_nothing(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs, product="outro")

    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.USAGE
    assert "outro produto" in envelope["error"]["message"]
    assert not (folder / "panel").exists()


@pytest.mark.parametrize("run_id", ["../x", "nao-e-run-id", "2026-11-13T05-15-32Z-vampi"])
def test_panel_refuses_an_invalid_run_id_without_echoing_it(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str], run_id: str
) -> None:
    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", run_id)

    assert code == ExitCode.USAGE
    assert run_id not in json.dumps(envelope)


def test_panel_works_with_only_the_files_that_exist(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)
    for name in ("run.json", "scan.json", "findings.json"):
        (folder / name).unlink()

    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert envelope["data"]["verdict"] == "partial"
    assert envelope["data"]["severe_findings"] is None
    assert envelope["data"]["sources"] == ["probe.json"]


def test_panel_survives_a_product_without_a_profile(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, products = world
    write_run(runs)
    (products / "vampi" / "target.yml").unlink()

    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    page = (runs / RUN_ID / "panel" / "summary.html").read_text(encoding="utf-8")
    assert "Cerca:" not in page
    assert envelope["data"]["verdict"] == "finished"


def test_the_panel_command_is_listed_in_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = invoke(capsys, "--help")

    assert code == ExitCode.OK
    assert "panel" in out


def journal_line(command: str, run_id: str | None, *, minute: int, state: str = "ok") -> str:
    start = datetime(2026, 11, 13, 23, 8, tzinfo=UTC) + timedelta(minutes=minute)
    record = {
        "schema_version": 1,
        "started_at": start.isoformat(),
        "finished_at": (start + timedelta(seconds=30)).isoformat(),
        "command": command,
        "product": "vampi",
        "run_id": run_id,
        "flags": [],
        "args": [],
        "exit_code": 0 if state == "ok" else 3,
        "state": state,
        "error_code": None if state == "ok" else "PREFLIGHT_FAILED",
        "summary": {"operations_sent": 30},
    }
    return json.dumps(record)


def test_panel_shows_the_commands_of_the_diary_in_the_terminal_page(
    world: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runs, _ = world
    folder = write_run(runs)
    state = tmp_path / "estado-do-diario"
    (state / "journal").mkdir(parents=True)
    lines = [
        journal_line("doctor", None, minute=0),
        journal_line("probe", RUN_ID, minute=1, state="erro"),
        "isto não é json",
    ]
    (state / "journal" / "vampi.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setenv("HDAST_STATE_DIR", str(state))

    code, _ = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    page = (folder / "panel" / "terminal.html").read_text(encoding="utf-8")
    assert "<code>$ hdast doctor vampi</code>" in page
    assert "<code>$ hdast probe vampi</code>" in page
    assert '<span class="chip ch-gr">erro</span>' in page
    assert "operations_sent: 30" in page
    assert "1 linha do diário estavam corrompidas" in page
    summary = (folder / "panel" / "summary.html").read_text(encoding="utf-8")
    assert "2 comandos, todos visíveis" in summary


def test_panel_without_a_diary_for_the_run_says_the_test_is_older_than_the_diary(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    code, _ = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    page = (folder / "panel" / "terminal.html").read_text(encoding="utf-8")
    assert "O diário de comandos começou na versão 1.2; este teste é anterior" in page
