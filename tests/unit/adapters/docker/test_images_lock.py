from pathlib import Path

import pytest

from harness_dast.adapters.docker.images_lock import has_build_contexts, load_images_lock
from harness_dast.domain.errors import ConfigError
from tests.fakes.host import published_images


def test_reads_lock_when_file_is_present(tmp_path: Path) -> None:
    lock = published_images()
    path = tmp_path / "images.lock.json"
    path.write_text(lock.model_dump_json(), encoding="utf-8")

    assert load_images_lock(path) == lock


def test_returns_none_when_file_is_absent(tmp_path: Path) -> None:
    assert load_images_lock(tmp_path / "images.lock.json") is None


@pytest.mark.parametrize("data", [b"{", b"{}", b"\xff", b" " * 4097])
def test_reports_config_error_when_lock_cannot_be_validated(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "images.lock.json"
    path.write_bytes(data)

    with pytest.raises(ConfigError, match=r"images\.lock\.json") as error:
        load_images_lock(path)

    assert error.value.hint


@pytest.mark.parametrize(("zap", "proxy"), [(True, False), (False, True), (True, True)])
def test_detects_clone_contexts_when_both_paths_exist(
    tmp_path: Path, zap: bool, proxy: bool
) -> None:
    if zap:
        (tmp_path / "docker/zap").mkdir(parents=True)
    if proxy:
        dockerfile = tmp_path / "docker/scope-proxy/Dockerfile"
        dockerfile.parent.mkdir(parents=True)
        dockerfile.touch()

    assert has_build_contexts(tmp_path) is (zap and proxy)
