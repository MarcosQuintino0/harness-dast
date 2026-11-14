"""Gravação do rascunho da tabela "quem pode o quê": cria, nunca sobrescreve (ADR 0041)."""

import os
from pathlib import Path

import pytest

from harness_dast.adapters.storage.authz_draft_writer import FileAuthzDraftWriter
from harness_dast.domain.authz_matrix_draft import DRAFT_FILE
from harness_dast.domain.errors import ConfigError


@pytest.fixture
def products(tmp_path: Path) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_text("product: demo\n", encoding="utf-8")
    return tmp_path


def test_creates_the_draft_in_the_product_folder_with_lf_line_endings(products: Path) -> None:
    path = FileAuthzDraftWriter(products).write_draft("demo", "a\nb\n")

    assert Path(path) == (products / "demo" / DRAFT_FILE).resolve()
    assert (products / "demo" / DRAFT_FILE).read_bytes() == b"a\nb\n"


def test_an_existing_draft_is_never_overwritten(products: Path) -> None:
    existing = products / "demo" / DRAFT_FILE
    existing.write_text("do dono\n", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        FileAuthzDraftWriter(products).write_draft("demo", "novo\n")

    assert "não é sobrescrito" in caught.value.message
    assert existing.read_text(encoding="utf-8") == "do dono\n"


def test_a_draft_that_is_a_link_to_the_target_never_overwrites_the_profile(products: Path) -> None:
    target = products / "demo" / "target.yml"
    try:
        os.symlink(target, products / "demo" / DRAFT_FILE)
    except OSError:
        pytest.skip("sem permissão para criar link simbólico neste ambiente")

    with pytest.raises(ConfigError):
        FileAuthzDraftWriter(products).write_draft("demo", "novo\n")

    assert target.read_text(encoding="utf-8") == "product: demo\n"


def test_an_unknown_or_invalid_product_is_a_config_error(products: Path) -> None:
    writer = FileAuthzDraftWriter(products)

    with pytest.raises(ConfigError):
        writer.write_draft("nao-existe", "x\n")
    with pytest.raises(ConfigError):
        writer.write_draft("../fora", "x\n")
