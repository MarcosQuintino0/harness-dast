"""Leitor dos caminhos do OpenAPI ao lado da carta (pedido mínimo, ADR 0120)."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi.spec_paths import FileSpecPaths
from harness_dast.domain.errors import ConfigError

SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Demo", "version": "1"},
    "servers": [{"url": "https://producao.acme.net.br"}],
    "paths": {
        "/users": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/users/{id}": {
            "get": {"responses": {"200": {"description": "ok"}}},
            "put": {"responses": {"200": {"description": "ok"}}},
        },
    },
}


def _spec(folder: Path, name: str = "openapi.json") -> None:
    (folder / name).write_text(json.dumps(SPEC), encoding="utf-8")


def test_read_paths_returns_each_path_once_in_document_order(tmp_path: Path) -> None:
    _spec(tmp_path)

    assert FileSpecPaths().read_paths(tmp_path, "openapi.json") == ("/users", "/users/{id}")


def test_read_paths_accepts_a_dot_slash_name_inside_the_folder(tmp_path: Path) -> None:
    _spec(tmp_path)

    assert FileSpecPaths().read_paths(tmp_path, "./openapi.json") == ("/users", "/users/{id}")


@pytest.mark.parametrize("relative", ["../openapi.json", "sub/../../openapi.json"])
def test_read_paths_refuses_a_file_outside_the_letter_folder(tmp_path: Path, relative: str) -> None:
    folder = tmp_path / "carta"
    folder.mkdir()
    _spec(tmp_path)

    with pytest.raises(ConfigError, match="ao lado da carta"):
        FileSpecPaths().read_paths(folder, relative)


def test_read_paths_refuses_an_absolute_path_to_another_folder(tmp_path: Path) -> None:
    folder = tmp_path / "carta"
    folder.mkdir()
    _spec(tmp_path)

    with pytest.raises(ConfigError, match="ao lado da carta"):
        FileSpecPaths().read_paths(folder, str(tmp_path / "openapi.json"))


def test_read_paths_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ao lado da carta"):
        FileSpecPaths().read_paths(tmp_path, "openapi.json")


def test_read_paths_refuses_a_file_that_is_not_an_openapi(tmp_path: Path) -> None:
    (tmp_path / "openapi.json").write_text("{ não é json", encoding="utf-8")

    with pytest.raises(ConfigError):
        FileSpecPaths().read_paths(tmp_path, "openapi.json")


def test_read_paths_never_returns_the_servers_block(tmp_path: Path) -> None:
    _spec(tmp_path)

    paths = FileSpecPaths().read_paths(tmp_path, "openapi.json")

    assert not any("producao" in path for path in paths)
