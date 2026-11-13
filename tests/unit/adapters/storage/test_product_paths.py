from pathlib import Path

import pytest

from harness_dast.adapters.storage.product_paths import (
    product_dir_path,
    resolve_products_dir,
    validate_product_name,
)
from harness_dast.domain.errors import ConfigError
from tests.fakes.fs_links import link_directory

BAD_NAMES = [
    "",
    "..",
    ".",
    "../x",
    "a/b",
    "a\\b",
    "/etc",
    "C:",
    "C:\\x",
    "c:x",
    "Demo",
    "-demo",
    "demo-",
    "de mo",
    "demo\n",
    "dëmo",
    "a" * 41,
    "con",
    "nul",
    "com1",
    "lpt9",
    "_template",
]


@pytest.mark.parametrize("name", BAD_NAMES)
def test_validate_product_name_rejects_unsafe_name(name: str) -> None:
    with pytest.raises(ConfigError) as caught:
        validate_product_name(name)

    assert len(name) < 4 or name not in caught.value.message


@pytest.mark.parametrize("name", ["demo", "meu-produto", "a", "x1-y2", "a" * 40])
def test_validate_product_name_accepts_slug(name: str) -> None:
    assert validate_product_name(name) == name


def test_resolve_products_dir_raises_when_directory_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        resolve_products_dir(tmp_path / "nao-existe")

    assert "--products-dir" in (caught.value.hint or "")


def test_resolve_products_dir_raises_when_path_is_a_file(tmp_path: Path) -> None:
    file = tmp_path / "arquivo"
    file.write_text("x", encoding="utf-8")

    with pytest.raises(ConfigError):
        resolve_products_dir(file)


def test_product_dir_path_stays_inside_products_dir(tmp_path: Path) -> None:
    result = product_dir_path(tmp_path, "demo")

    assert result == tmp_path.resolve() / "demo"


def test_product_dir_path_works_when_products_dir_is_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert product_dir_path(Path("."), "demo") == tmp_path.resolve() / "demo"


def test_product_dir_path_rejects_symlink_that_leaves_products_dir(tmp_path: Path) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    products = tmp_path / "produtos"
    products.mkdir()
    link = products / "demo"
    link_directory(link, outside)

    with pytest.raises(ConfigError) as caught:
        product_dir_path(products, "demo")

    assert "fora" in caught.value.message
