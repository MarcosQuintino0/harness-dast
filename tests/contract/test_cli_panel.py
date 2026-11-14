"""Contrato de `hdast panel`: envelope JSON, códigos de saída, páginas gravadas e erros de uso."""

import json
import re
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


# ------------------------------------------------------------ índices (ADR 0034)


def hrefs(page: str) -> list[str]:
    return re.findall(r'href="([^"]*)"', page)


def test_panel_also_writes_the_indexes_and_the_path_links_reach_files_that_exist(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    code, envelope = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    assert envelope["data"]["indexes"] == ["index.html", "history-vampi.html"]
    panel = folder / "panel"
    for name in envelope["data"]["files"]:
        for link in hrefs((folder / name).read_text(encoding="utf-8")):
            target = link.split("#", 1)[0]  # vazio: âncora na própria página
            assert not target or (panel / target).resolve().is_file(), (name, link)
    index = (runs / "index.html").read_text(encoding="utf-8")
    history = (runs / "history-vampi.html").read_text(encoding="utf-8")
    for page in (index, history):
        for link in hrefs(page):
            assert (runs / link).is_file(), link
    assert "<script" not in index + history


def test_the_index_only_mode_rebuilds_the_indexes_without_touching_the_test_panels(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    code, envelope = invoke_json(capsys, "panel", "--index")

    assert code == ExitCode.OK
    assert envelope["data"] == {"indexes": ["index.html", "history-vampi.html"]}
    assert not (folder / "panel").exists()
    assert "sem painel" in (runs / "history-vampi.html").read_text(encoding="utf-8")


def test_the_index_only_mode_on_an_empty_runs_folder_says_there_is_no_product(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world

    code, out, _ = invoke(capsys, "panel", "--index")

    assert code == ExitCode.OK
    assert "index.html" in out
    assert "Nenhum produto testado ainda" in (runs / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("extra", [["vampi"], ["--run", RUN_ID]])
def test_the_index_flag_alone_refuses_a_product_or_a_run(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    code, envelope = invoke_json(capsys, "panel", "--index", *extra)

    assert code == ExitCode.USAGE
    assert envelope["error"]["hint"]


def test_panel_without_a_product_and_without_the_index_flag_is_a_usage_error(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code, envelope = invoke_json(capsys, "panel")

    assert code == ExitCode.USAGE
    assert "--index" in envelope["error"]["message"]


def test_a_corrupted_run_folder_does_not_break_the_index(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    write_run(runs)
    broken = runs / "2026-11-12T05-15-32Z-vampi-cd34"
    broken.mkdir()
    (broken / "run.json").write_text("{isto nao e json", encoding="utf-8")
    (runs / "pasta-qualquer").mkdir()

    code, _ = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    history = (runs / "history-vampi.html").read_text(encoding="utf-8")
    assert "sem dados" in history
    assert history.count("<tr") == 3


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
    assert (runs / "index.html").is_file()  # o diário e os índices saem pelo mesmo comando
    assert (runs / "history-vampi.html").is_file()


def test_panel_without_a_diary_for_the_run_says_the_test_is_older_than_the_diary(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    folder = write_run(runs)

    code, _ = invoke_json(capsys, "panel", "vampi", "--run", RUN_ID)

    assert code == ExitCode.OK
    page = (folder / "panel" / "terminal.html").read_text(encoding="utf-8")
    assert "O diário de comandos começou na versão 1.2; este teste é anterior" in page


def test_every_relative_link_of_every_generated_page_reaches_an_existing_file_and_anchor(
    world: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    runs, _ = world
    other_run = "2026-11-12T05-15-32Z-vampi-cd34"
    stranger_run = "2026-11-12T06-00-00Z-outro-ab12"
    for run_id, product in ((RUN_ID, "vampi"), (other_run, "vampi"), (stranger_run, "outro")):
        folder = write_run(runs, run_id, product=product)
        (folder / "report.html").write_text("<html></html>", encoding="utf-8")
    for run_id in (RUN_ID, other_run):
        assert invoke_json(capsys, "panel", "vampi", "--run", run_id)[0] == ExitCode.OK

    pages = sorted(runs.rglob("*.html"))
    assert (runs / "index.html") in pages
    assert (runs / "history-vampi.html") in pages
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if page.parent == runs / RUN_ID / "panel":  # teste terminado: nenhuma aba apagada
            assert 'class="off"' not in text, page
        for link in hrefs(text):
            target, _, anchor = link.partition("#")
            destination = (page.parent / target) if target else page
            assert destination.is_file(), (page.name, link)
            if anchor:
                assert f'id="{anchor}"' in destination.read_text(encoding="utf-8"), (page, link)
