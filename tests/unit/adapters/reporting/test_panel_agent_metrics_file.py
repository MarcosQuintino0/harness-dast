"""`agent-metrics.json` no painel: leitura tolerante (nunca derruba, nunca inventa)."""

from pathlib import Path

import pytest

from harness_dast.adapters.reporting.panel_files import FilePanelFiles
from harness_dast.domain.errors import ConfigError
from tests.unit.domain.report_helpers import RUN_ID


@pytest.fixture
def files(tmp_path: Path) -> FilePanelFiles:
    return FilePanelFiles(tmp_path)


def write_agent(tmp_path: Path, text: str) -> None:
    folder = tmp_path / RUN_ID
    folder.mkdir(exist_ok=True)
    (folder / "agent-metrics.json").write_text(text, encoding="utf-8")


def test_agent_metrics_are_none_when_the_file_does_not_exist(files: FilePanelFiles) -> None:
    assert files.read_agent_metrics(RUN_ID) is None


def test_agent_metrics_are_read_and_unknown_fields_are_ignored(
    tmp_path: Path, files: FilePanelFiles
) -> None:
    write_agent(
        tmp_path,
        '{"schema_version": 1, "model": "m", "label": "x", "loops": {}, '
        '"totals": {"turns": 3, "tokens": {"input": 1, "output": 2, '
        '"cache_creation": 3, "cache_read": 4}}, "stages": {"alcance": {"seconds": 1.5}}}',
    )

    loaded = files.read_agent_metrics(RUN_ID)

    assert loaded is not None
    assert loaded.model == "m"
    assert loaded.totals is not None
    assert loaded.totals.tokens is not None
    assert loaded.totals.tokens.counted == 6
    assert loaded.stages["alcance"].tokens is None


@pytest.mark.parametrize(
    "text",
    [
        "{ não é json",
        "[]",
        '{"schema_version": 2}',
        '{"schema_version": 1, "totals": {"tokens": {"input": -3}}}',
        '{"model": "sem versão"}',
        "",
    ],
)
def test_agent_metrics_that_cannot_be_used_are_none_not_an_error(
    tmp_path: Path, files: FilePanelFiles, text: str
) -> None:
    write_agent(tmp_path, text)

    assert files.read_agent_metrics(RUN_ID) is None


def test_agent_metrics_in_a_non_utf8_file_are_none(tmp_path: Path, files: FilePanelFiles) -> None:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    (folder / "agent-metrics.json").write_bytes(b"\xff\xfe\x00{")

    assert files.read_agent_metrics(RUN_ID) is None


def test_agent_metrics_with_an_invalid_run_id_are_refused(files: FilePanelFiles) -> None:
    with pytest.raises(ConfigError):
        files.read_agent_metrics("../../etc")
