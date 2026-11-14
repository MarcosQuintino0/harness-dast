"""Pasta `runs/` dos índices: lista só `run_id`, grava só os dois nomes de índice, atômico."""

from pathlib import Path

import pytest

from harness_dast.adapters.reporting.panel_index_files import FilePanelIndexFiles
from harness_dast.application.panel_index_ports import RunFolder
from harness_dast.domain.errors import ConfigError

NEW = "2026-11-13T20-08-00Z-vampi-cd34"
OLD = "2026-11-12T20-08-00Z-clinica-piloto-ab12"


@pytest.fixture
def files(tmp_path: Path) -> FilePanelIndexFiles:
    return FilePanelIndexFiles(tmp_path)


def test_lists_only_folders_named_as_a_run_id_with_the_product_taken_from_the_name(
    tmp_path: Path, files: FilePanelIndexFiles
) -> None:
    (tmp_path / NEW).mkdir()
    (tmp_path / OLD).mkdir()
    (tmp_path / "qualquer-pasta").mkdir()
    (tmp_path / "2026-11-13T20-08-00Z-sem-sufixo").mkdir()
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "2026-11-13T20-08-00Z-vampi-ef56").write_text(
        "arquivo, nao pasta", encoding="utf-8"
    )

    found = files.list_runs()

    assert found == (RunFolder(OLD, "clinica-piloto"), RunFolder(NEW, "vampi"))


def test_a_missing_runs_folder_lists_nothing(tmp_path: Path) -> None:
    assert FilePanelIndexFiles(tmp_path / "nao-existe").list_runs() == ()


def test_has_panel_only_when_the_summary_page_exists(
    tmp_path: Path, files: FilePanelIndexFiles
) -> None:
    (tmp_path / NEW / "panel").mkdir(parents=True)
    (tmp_path / OLD).mkdir()
    (tmp_path / NEW / "panel" / "summary.html").write_text("x", encoding="utf-8")

    assert files.has_panel(NEW)
    assert not files.has_panel(OLD)
    assert not files.has_panel("../x")


def test_writes_the_indexes_atomically_and_leaves_no_temporary_file(
    tmp_path: Path, files: FilePanelIndexFiles
) -> None:
    assert files.write_index("index.html", "<p>um</p>") == "index.html"
    files.write_index("index.html", "<p>dois</p>")
    files.write_index("history-vampi.html", "<p>h</p>")

    assert (tmp_path / "index.html").read_text(encoding="utf-8") == "<p>dois</p>"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["history-vampi.html", "index.html"]


def test_creates_the_runs_folder_when_it_does_not_exist_yet(tmp_path: Path) -> None:
    files = FilePanelIndexFiles(tmp_path / "runs")

    files.write_index("index.html", "x")

    assert (tmp_path / "runs" / "index.html").is_file()


@pytest.mark.parametrize(
    "name",
    ["../index.html", "a/b.html", "history-.html", "history-../x.html", "outro.html", "INDEX.html"],
)
def test_refuses_a_name_that_is_not_an_index(files: FilePanelIndexFiles, name: str) -> None:
    with pytest.raises(ConfigError):
        files.write_index(name, "x")


def test_a_write_failure_is_a_config_error_with_a_hint(tmp_path: Path) -> None:
    blocked = tmp_path / "runs"
    blocked.write_text("sou um arquivo, nao uma pasta", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        FilePanelIndexFiles(blocked).write_index("index.html", "x")

    assert caught.value.hint
