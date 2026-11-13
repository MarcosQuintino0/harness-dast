"""Leitura de `data-rules.yml` e `flows.yml` e hashes dos arquivos do produto."""

import hashlib
from pathlib import Path

import pytest

from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.domain.errors import ConfigError
from tests.fakes.fs_links import link_directory
from tests.fakes.profile_data import dump_yaml, valid_profile, valid_profile_data

RULES = (
    "schema_version: 1\nrules:\n  - match: { field: cpf }\n    generator: br.cpf\n"
    "    unique: true\n"
)
FLOWS = (
    "schema_version: 1\nbindings:\n  - produces: { operation: criar, field: id }\n"
    "    consumed_by:\n      - { operation: buscar, param: pacienteId }\n"
)


@pytest.fixture
def product(tmp_path: Path) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "target.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    return folder


def docs(product: Path) -> FileProductDocuments:
    return FileProductDocuments(product.parent)


def test_missing_files_give_none(product: Path) -> None:
    assert docs(product).load_data_rules("demo") is None
    assert docs(product).load_flows("demo") is None


def test_valid_files_are_loaded_and_validated(product: Path) -> None:
    (product / "data-rules.yml").write_text(RULES, encoding="utf-8")
    (product / "flows.yml").write_text(FLOWS, encoding="utf-8")

    rules = docs(product).load_data_rules("demo")
    flows = docs(product).load_flows("demo")

    assert rules is not None
    assert rules.rules[0].generator == "br.cpf"
    assert flows is not None
    assert flows.bindings[0].produces.operation == "criar"


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("", "data-rules.yml está vazio"),
        ("- lista\n", "raiz do data-rules.yml"),
        ("a: &x 1\nb: *x\n", "âncora"),
        ("schema_version: 1\nschema_version: 1\n", "repetida"),
        ("a: [\n", "data-rules.yml não é um YAML válido"),
        (
            "schema_version: 1\nrules:\n  - match: { field: x }\n    generator: inexistente\n",
            "rules[0]",
        ),
        ("schema_version: 2\nrules: []\n", "schema_version"),
    ],
)
def test_malformed_rules_are_config_errors_that_name_the_file(
    product: Path, text: str, fragment: str
) -> None:
    (product / "data-rules.yml").write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError) as info:
        docs(product).load_data_rules("demo")

    assert fragment in info.value.message


def test_flows_errors_name_the_flows_file(product: Path) -> None:
    (product / "flows.yml").write_text("x: &a 1\ny: *a\n", encoding="utf-8")

    with pytest.raises(ConfigError) as info:
        docs(product).load_flows("demo")

    assert "flows.yml" in info.value.message


def test_oversized_and_non_utf8_files_are_refused_without_echoing_content(product: Path) -> None:
    (product / "data-rules.yml").write_bytes(b"#" + b"x" * (300 * 1024))
    with pytest.raises(ConfigError, match="grande demais"):
        docs(product).load_data_rules("demo")

    (product / "data-rules.yml").write_bytes(b"\xff\xfe\x00segredo")
    with pytest.raises(ConfigError) as info:
        docs(product).load_data_rules("demo")
    assert "UTF-8" in info.value.message
    assert "segredo" not in info.value.message


def test_a_bom_is_accepted(product: Path) -> None:
    (product / "data-rules.yml").write_bytes(b"\xef\xbb\xbf" + RULES.encode())

    assert docs(product).load_data_rules("demo") is not None


def test_a_file_reached_through_a_link_outside_the_product_folder_is_refused(
    product: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "fora"
    outside.mkdir()
    (outside / "data-rules.yml").write_text(RULES, encoding="utf-8")
    link_directory(product / "atalho", outside)

    with pytest.raises(ConfigError, match="fora da pasta"):
        resolve_product_file(product.parent, "demo", "atalho/data-rules.yml")


def test_hashes_are_the_sha256_of_each_input_and_none_for_absent_files(product: Path) -> None:
    (product / "openapi.json").write_text('{"openapi":"3.0.0"}', encoding="utf-8")
    (product / "flows.yml").write_bytes(FLOWS.encode())

    hashes = docs(product).hashes("demo", valid_profile())

    assert hashes.target_yml == hashlib.sha256((product / "target.yml").read_bytes()).hexdigest()
    assert hashes.openapi == hashlib.sha256(b'{"openapi":"3.0.0"}').hexdigest()
    assert hashes.flows == hashlib.sha256(FLOWS.encode()).hexdigest()
    assert hashes.data_rules is None


def test_resolve_product_file_keeps_files_inside_the_product_folder(product: Path) -> None:
    assert (
        resolve_product_file(product.parent, "demo", "./openapi.json")
        == (product / "openapi.json").resolve()
    )
    with pytest.raises(ConfigError):
        resolve_product_file(product.parent, "Nome Inválido", "x")
    with pytest.raises(ConfigError, match="fora da pasta"):
        resolve_product_file(product.parent, "demo", "../outro/x")
