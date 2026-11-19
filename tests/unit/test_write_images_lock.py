import json
from pathlib import Path

import pytest

from scripts.write_images_lock import main

ZAP = "ghcr.io/example/hdast-zap@sha256:" + "a" * 64
PROXY = "ghcr.io/example/hdast-scope-proxy@sha256:" + "b" * 64


def test_writes_both_images_when_arguments_are_valid(tmp_path: Path) -> None:
    path = tmp_path / "images.lock.json"

    main(["1.12.2", ZAP, PROXY, "--output", str(path)])

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "version": "1.12.2",
        "images": {
            "zap": {
                "repository": "ghcr.io/example/hdast-zap",
                "tag": "1.12.2",
                "digest": "sha256:" + "a" * 64,
            },
            "scope_proxy": {
                "repository": "ghcr.io/example/hdast-scope-proxy",
                "tag": "1.12.2",
                "digest": "sha256:" + "b" * 64,
            },
        },
    }


@pytest.mark.parametrize(
    "args",
    [
        ["1.12.2", ZAP],
        ["", ZAP, PROXY],
        ["1.12.2", ZAP.partition("@")[0], PROXY],
        ["1.12.2", ZAP, PROXY[:-1]],
        ["1.12.2", ZAP.replace("@", ":latest@"), PROXY],
    ],
)
def test_keeps_previous_file_when_arguments_are_invalid(tmp_path: Path, args: list[str]) -> None:
    path = tmp_path / "images.lock.json"
    path.write_text("publicação anterior", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main([*args, "--output", str(path)])

    assert error.value.code == 2
    assert path.read_text(encoding="utf-8") == "publicação anterior"
