"""Leitor dos padrões mínimos gravados no cabeçalho do `target.yml` (ADR 0114)."""

from pathlib import Path

import pytest

from harness_dast.adapters.storage.applied_defaults import FileAppliedDefaults
from harness_dast.domain.errors import ConfigError

NOTE = "# Padrão mínimo da CLI: limits.max_duration_minutes = 30 (resposta 'não sei' na carta)\n"


def _product(tmp_path: Path, text: str) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_text(text, encoding="utf-8")
    return tmp_path


def test_read_returns_the_applied_defaults_from_the_header(tmp_path: Path) -> None:
    root = _product(tmp_path, "# gerado\n" + NOTE + "schema_version: 1\n")

    assert FileAppliedDefaults(root).read("demo") == ("limits.max_duration_minutes = 30",)


def test_read_returns_nothing_when_the_profile_has_no_notes(tmp_path: Path) -> None:
    root = _product(tmp_path, "schema_version: 1\n")

    assert FileAppliedDefaults(root).read("demo") == ()


def test_read_accepts_a_byte_order_mark(tmp_path: Path) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_bytes(b"\xef\xbb\xbf" + NOTE.encode("utf-8"))

    assert FileAppliedDefaults(tmp_path).read("demo") == ("limits.max_duration_minutes = 30",)


def test_read_raises_when_the_profile_is_missing(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()

    with pytest.raises(ConfigError, match=r"não tem target.yml"):
        FileAppliedDefaults(tmp_path).read("demo")


def test_read_raises_when_the_profile_is_not_utf8(tmp_path: Path) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(ConfigError, match="UTF-8"):
        FileAppliedDefaults(tmp_path).read("demo")


@pytest.mark.parametrize("product", ["../fora", "", "COM ESPACO"])
def test_read_raises_on_an_invalid_product_name(tmp_path: Path, product: str) -> None:
    with pytest.raises(ConfigError):
        FileAppliedDefaults(tmp_path).read(product)
