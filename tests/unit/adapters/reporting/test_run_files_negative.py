"""`negative.json` em disco: leitura estrita (ausente é `None`), escrita atômica, sem eco."""

from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from tests.unit.domain.negative_samples import RUN_ID, negative_result


@pytest.fixture
def store(tmp_path: Path) -> FileRunArtifacts:
    return FileRunArtifacts(tmp_path)


def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / RUN_ID
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_missing_negative_json_means_the_stage_did_not_run(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    run_dir(tmp_path)

    assert store.read_negative(RUN_ID) is None


def test_negative_result_round_trips_and_no_temporary_file_is_left(
    tmp_path: Path, store: FileRunArtifacts
) -> None:
    result = negative_result()
    run_dir(tmp_path)

    store.write_negative(RUN_ID, result)

    assert store.read_negative(RUN_ID) == result
    assert sorted(p.name for p in run_dir(tmp_path).iterdir()) == ["negative.json"]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{nao e json",
        "[]",
        "null",
        '{"run_id": 1}',
        '{"schema_version": 1, "run_id": "r", "product": "p", "findings": [1]}',
    ],
)
def test_a_corrupt_negative_json_is_a_config_error_without_echoing_content(
    tmp_path: Path, store: FileRunArtifacts, content: str
) -> None:
    (run_dir(tmp_path) / "negative.json").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError) as info:
        store.read_negative(RUN_ID)

    assert "ilegível" in info.value.message
    assert content.strip() == "" or content.strip() not in info.value.message


def test_a_non_utf8_negative_json_is_refused(tmp_path: Path, store: FileRunArtifacts) -> None:
    (run_dir(tmp_path) / "negative.json").write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(ConfigError, match="ilegível"):
        store.read_negative(RUN_ID)
