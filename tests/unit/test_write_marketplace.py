from pathlib import Path

import pytest

from scripts.write_marketplace import MARKETPLACE_PATH, Marketplace, main

ROOT = Path(__file__).resolve().parents[2]
TAG = "v2.3.4"
SHA = "a1b2" * 10


@pytest.fixture
def marketplace_path(tmp_path: Path) -> Path:
    path = tmp_path / "marketplace.json"
    path.write_bytes((ROOT / MARKETPLACE_PATH).read_bytes())
    return path


def test_updates_only_ref_and_sha_when_valid(marketplace_path: Path) -> None:
    previous = Marketplace.model_validate_json(marketplace_path.read_bytes()).model_dump()
    previous["plugins"][0]["source"].update(ref=TAG, sha=SHA)

    main([TAG, SHA, "--path", str(marketplace_path)])

    updated = Marketplace.model_validate_json(marketplace_path.read_bytes())
    assert updated.model_dump() == previous


@pytest.mark.parametrize("arguments", [[TAG[1:], SHA], [TAG, SHA[:-1]], [TAG]])
def test_keeps_manifest_when_arguments_are_invalid(
    marketplace_path: Path, arguments: list[str]
) -> None:
    previous = marketplace_path.read_bytes()

    with pytest.raises(SystemExit) as error:
        main([*arguments, "--path", str(marketplace_path)])

    assert error.value.code == 2
    assert marketplace_path.read_bytes() == previous


@pytest.mark.parametrize("invalid_content", [b"{", b"{}", b"\xff"])
def test_keeps_manifest_when_content_is_invalid(tmp_path: Path, invalid_content: bytes) -> None:
    path = tmp_path / "marketplace.json"
    path.write_bytes(invalid_content)

    with pytest.raises(SystemExit) as error:
        main([TAG, SHA, "--path", str(path)])

    assert error.value.code == 2
    assert path.read_bytes() == invalid_content
