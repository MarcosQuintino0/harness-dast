import os
import shutil
from pathlib import Path

import pytest

from harness_dast.adapters.storage.product_scaffolder import (
    FileProductScaffolder,
    default_template_dir,
)
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.domain.errors import ConfigError

TEMPLATE_FILES = (
    "README.md",
    "cleanup/README.md",
    "cleanup/cleanup.sql.example",
    "data-rules.yml",
    "flows.yml",
    "target.yml",
)


@pytest.fixture
def products(tmp_path: Path) -> Path:
    directory = tmp_path / "produtos"
    directory.mkdir()
    return directory


def _scaffolder(products: Path) -> FileProductScaffolder:
    return FileProductScaffolder(products, default_template_dir())


def test_default_template_dir_points_to_the_repository_template() -> None:
    assert (default_template_dir() / "target.yml").is_file()


def test_scaffold_copies_template_files_when_product_is_new(products: Path) -> None:
    result = _scaffolder(products).scaffold("demo")

    assert result.files == TEMPLATE_FILES
    assert Path(result.directory) == (products / "demo").resolve()
    for name in TEMPLATE_FILES:
        assert (products / "demo" / name).is_file()


def test_scaffold_sets_product_name_in_target_yml(products: Path) -> None:
    _scaffolder(products).scaffold("meu-app")

    text = (products / "meu-app" / "target.yml").read_text(encoding="utf-8")
    assert "\nproduct: meu-app\n" in text
    assert "meu-produto\n" not in text.split("environment:")[0].split("product:")[1][:20]


def test_scaffold_writes_lf_line_endings(products: Path) -> None:
    _scaffolder(products).scaffold("demo")

    assert b"\r" not in (products / "demo" / "target.yml").read_bytes()


def test_scaffold_does_not_modify_the_template(products: Path) -> None:
    before = (default_template_dir() / "target.yml").read_bytes()

    _scaffolder(products).scaffold("demo")

    assert (default_template_dir() / "target.yml").read_bytes() == before


def test_scaffold_refuses_to_overwrite_existing_product(products: Path) -> None:
    existing = products / "demo"
    existing.mkdir()
    (existing / "target.yml").write_text("meu trabalho", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        _scaffolder(products).scaffold("demo")

    assert "já existe" in caught.value.message
    assert (existing / "target.yml").read_text(encoding="utf-8") == "meu trabalho"
    assert [p.name for p in existing.iterdir()] == ["target.yml"]


def test_scaffold_refuses_existing_product_even_when_folder_is_empty(products: Path) -> None:
    (products / "demo").mkdir()

    with pytest.raises(ConfigError):
        _scaffolder(products).scaffold("demo")


@pytest.mark.parametrize("name", ["../fora", "a/b", "..", "/abs", "C:\\x", "Demo", ""])
def test_scaffold_creates_nothing_when_name_is_unsafe(products: Path, name: str) -> None:
    with pytest.raises(ConfigError):
        _scaffolder(products).scaffold(name)

    assert list(products.parent.iterdir()) == [products]
    assert list(products.iterdir()) == []


def test_scaffold_raises_when_products_dir_does_not_exist(tmp_path: Path) -> None:
    missing = tmp_path / "nao-existe"

    with pytest.raises(ConfigError):
        FileProductScaffolder(missing, default_template_dir()).scaffold("demo")

    assert not missing.exists()


def test_scaffold_raises_when_template_is_missing(products: Path, tmp_path: Path) -> None:
    scaffolder = FileProductScaffolder(products, tmp_path / "sem-modelo")

    with pytest.raises(ConfigError) as caught:
        scaffolder.scaffold("demo")

    assert "modelo" in caught.value.message
    assert list(products.iterdir()) == []


def test_scaffold_removes_partial_folder_when_template_is_altered(
    products: Path, tmp_path: Path
) -> None:
    template = tmp_path / "modelo"
    template.mkdir()
    (template / "a.txt").write_text("a", encoding="utf-8")
    (template / "target.yml").write_text("product: outro-nome\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        FileProductScaffolder(products, template).scaffold("demo")

    assert list(products.iterdir()) == []


def test_scaffold_removes_partial_folder_when_copy_fails(
    products: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_copy(*args: object, **kwargs: object) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(shutil, "copyfile", broken_copy)

    with pytest.raises(ConfigError) as caught:
        _scaffolder(products).scaffold("demo")

    assert "parcial" in caught.value.message
    assert list(products.iterdir()) == []


def test_scaffold_skips_symlinks_found_in_the_template(products: Path, tmp_path: Path) -> None:
    template = tmp_path / "modelo"
    template.mkdir()
    (template / "target.yml").write_text("product: meu-produto\n", encoding="utf-8")
    secret = tmp_path / "segredo.txt"
    secret.write_text("conteudo", encoding="utf-8")
    try:
        os.symlink(secret, template / "link.txt")
    except OSError:
        pytest.skip("sem permissão para criar link simbólico neste ambiente")

    result = FileProductScaffolder(products, template).scaffold("demo")

    assert result.files == ("target.yml",)


def test_scaffolded_template_is_structurally_valid_for_the_loader(products: Path) -> None:
    _scaffolder(products).scaffold("demo")

    profile = FileProfileRepository(products).load("demo")

    assert profile.product == "demo"
