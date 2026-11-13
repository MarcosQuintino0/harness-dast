"""Leitor do OpenAPI do produto."""

from pathlib import Path

import pytest

from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.domain.errors import ConfigError
from tests.fakes.profile_data import valid_profile

VAMPI = Path(__file__).parents[3] / "fixtures" / "specs" / "vampi.yml"


def loader(products: Path) -> FileSpecLoader:
    return FileSpecLoader(
        lambda product, relative: resolve_product_file(products, product, relative)
    )


def test_the_openapi_named_by_the_profile_is_loaded_from_the_product_folder(tmp_path: Path) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "openapi.yml").write_bytes(VAMPI.read_bytes())
    profile = valid_profile("demo").model_copy(update={"openapi": "./openapi.yml"})

    spec = loader(tmp_path).load("demo", profile)

    assert spec.title == "VAmPI"
    assert len(spec.operations) == 14


def test_a_missing_openapi_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()

    with pytest.raises(ConfigError) as info:
        loader(tmp_path).load("demo", valid_profile("demo"))

    assert info.value.hint


def test_an_openapi_outside_the_product_folder_is_refused(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    profile = valid_profile("demo").model_copy(update={"openapi": "../outro/openapi.json"})

    with pytest.raises(ConfigError, match="fora da pasta"):
        loader(tmp_path).load("demo", profile)
