import os
from pathlib import Path

import pytest

from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES
from harness_dast.domain.errors import ConfigError
from tests.fakes.fs_links import link_directory
from tests.fakes.profile_data import dump_yaml, valid_profile_data

SECRET = "SenhaLiteral-Nao-Pode-Vazar-9"  # noqa: S105 - sentinela para provar que não vaza


@pytest.fixture
def products(tmp_path: Path) -> Path:
    return tmp_path


def _write(products: Path, text: str | bytes, product: str = "demo") -> Path:
    directory = products / product
    directory.mkdir(exist_ok=True)
    target = directory / "target.yml"
    if isinstance(text, bytes):
        target.write_bytes(text)
    else:
        target.write_text(text, encoding="utf-8", newline="")
    return directory


def _write_valid(products: Path, *, with_cleanup: bool = False) -> Path:
    return _write(products, dump_yaml(valid_profile_data(with_cleanup=with_cleanup)))


def _error(products: Path, product: str = "demo") -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        FileProfileRepository(products).load(product)
    return caught.value


def test_load_returns_profile_when_file_is_valid(products: Path) -> None:
    _write_valid(products)

    profile = FileProfileRepository(products).load("demo")

    assert profile.product == "demo"
    assert profile.environment.name == "homolog"


def test_load_accepts_utf8_bom(products: Path) -> None:
    text = dump_yaml(valid_profile_data())
    _write(products, b"\xef\xbb\xbf" + text.encode("utf-8"))

    assert FileProfileRepository(products).load("demo").product == "demo"


def test_load_accepts_crlf_line_endings(products: Path) -> None:
    text = dump_yaml(valid_profile_data()).replace("\n", "\r\n")
    _write(products, text.encode("utf-8"))

    assert FileProfileRepository(products).load("demo").product == "demo"


def test_load_raises_when_products_dir_is_missing(tmp_path: Path) -> None:
    error = _error(tmp_path / "nao-existe")

    assert "pasta de produtos" in error.message


def test_load_raises_with_init_hint_when_product_folder_is_missing(products: Path) -> None:
    error = _error(products)

    assert "não existe" in error.message
    assert "hdast init" in (error.hint or "")


def test_load_raises_when_target_yml_is_missing(products: Path) -> None:
    (products / "demo").mkdir()

    assert "target.yml" in _error(products).message


def test_load_raises_when_target_yml_is_a_directory(products: Path) -> None:
    (products / "demo" / "target.yml").mkdir(parents=True)

    assert "target.yml" in _error(products).message


def test_load_raises_when_file_is_empty(products: Path) -> None:
    _write(products, "")

    assert "vazio" in _error(products).message


def test_load_raises_when_file_is_not_utf8(products: Path) -> None:
    _write(products, b"product: caf\xe9\n")

    assert "UTF-8" in _error(products).message


def test_load_raises_when_file_is_too_large(products: Path) -> None:
    _write(products, "# " + "x" * MAX_PROFILE_BYTES + "\n")

    assert "grande demais" in _error(products).message


def test_load_accepts_file_at_exactly_the_size_limit(products: Path) -> None:
    text = dump_yaml(valid_profile_data())
    padding = "#" * (MAX_PROFILE_BYTES - len(text.encode("utf-8")) - 1) + "\n"
    _write(products, text + padding)

    assert FileProfileRepository(products).load("demo").product == "demo"


def test_load_raises_when_file_cannot_be_read(
    products: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_valid(products)

    def deny(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("negado")

    monkeypatch.setattr(Path, "open", deny)

    assert "ler" in _error(products).message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: &x 1\n", "âncora"),
        ("a: 1\na: 2\n", "repetida"),
        ("a:\n  <<: {b: 1}\n", "mesclagem"),
        ("a: !!python/object:os.system {}\n", "tag"),
        ("- 1\n", "mapa"),
    ],
)
def test_load_rejects_dangerous_yaml(products: Path, text: str, expected: str) -> None:
    _write(products, text)

    assert expected in _error(products).message


def test_load_raises_when_schema_is_invalid(products: Path) -> None:
    data = valid_profile_data()
    data["limits"]["requests_per_second"] = 9999
    _write(products, dump_yaml(data))

    error = _error(products)

    assert "limits.requests_per_second" in error.message


def test_load_never_echoes_literal_secret_when_it_is_in_a_secret_field(products: Path) -> None:
    data = valid_profile_data()
    data["auth"]["accounts"][0]["password"] = {"secret_ref": SECRET}
    data["auth"]["accounts"][0]["username"] = SECRET
    _write(products, dump_yaml(data))

    error = _error(products)

    assert SECRET not in f"{error.message} {error.hint}"
    assert SECRET not in repr(error)


def test_load_never_echoes_secret_when_yaml_is_malformed(products: Path) -> None:
    _write(products, f"password: {SECRET}\n  bad: [\n")

    error = _error(products)

    assert SECRET not in f"{error.message} {error.hint}"


def test_load_raises_when_product_field_differs_from_folder_name(products: Path) -> None:
    _write(products, dump_yaml(valid_profile_data("outro")), product="demo")

    error = _error(products)

    assert "não confere" in error.message
    assert "demo" in (error.hint or "")


@pytest.mark.parametrize("name", ["../fora", "a/b", "..", "C:\\x", "/etc/passwd", ""])
def test_load_rejects_unsafe_product_name_without_touching_disk(products: Path, name: str) -> None:
    error = _error(products, name)

    assert "inválido" in error.message


def test_load_raises_when_target_yml_is_a_symlink_to_outside(
    products: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "externo"
    outside.mkdir()
    (outside / "alvo.yml").write_text(dump_yaml(valid_profile_data()), encoding="utf-8")
    directory = products / "demo"
    directory.mkdir()
    try:
        os.symlink(outside / "alvo.yml", directory / "target.yml")
    except OSError:
        pytest.skip("sem permissão para criar link simbólico neste ambiente")

    assert "fora da pasta" in _error(products).message


def test_load_raises_when_openapi_goes_through_a_link_to_outside(
    products: Path, tmp_path: Path
) -> None:
    data = valid_profile_data()
    data["openapi"] = "./docs/openapi.json"
    directory = _write(products, dump_yaml(data))
    outside = tmp_path / "externo"
    outside.mkdir()
    (outside / "openapi.json").write_text("{}", encoding="utf-8")
    link_directory(directory / "docs", outside)

    error = _error(products)

    assert "openapi" in error.message
    assert "sai da pasta" in error.message


def test_load_raises_when_cleanup_script_goes_through_a_link_to_outside(
    products: Path, tmp_path: Path
) -> None:
    directory = _write_valid(products, with_cleanup=True)
    outside = tmp_path / "externo"
    outside.mkdir()
    (outside / "cleanup.sql").write_text("delete from t;", encoding="utf-8")
    link_directory(directory / "cleanup", outside)

    assert "cleanup.script" in _error(products).message


def test_load_rejects_openapi_path_with_parent_reference_through_the_domain(
    products: Path,
) -> None:
    data = valid_profile_data()
    data["openapi"] = "../../segredo.json"
    _write(products, dump_yaml(data))

    assert "openapi" in _error(products).message


def test_missing_files_lists_files_that_do_not_exist(products: Path) -> None:
    _write_valid(products, with_cleanup=True)
    repository = FileProfileRepository(products)
    profile = repository.load("demo")

    missing = repository.missing_files("demo", profile)

    assert [(m.field, m.path) for m in missing] == [
        ("openapi", "./openapi.json"),
        ("cleanup.script", "./cleanup/cleanup.sql"),
    ]


def test_missing_files_is_empty_when_files_exist(products: Path) -> None:
    directory = _write_valid(products, with_cleanup=True)
    (directory / "openapi.json").write_text("{}", encoding="utf-8")
    (directory / "cleanup").mkdir()
    (directory / "cleanup" / "cleanup.sql").write_text("-- x", encoding="utf-8")
    repository = FileProfileRepository(products)

    assert repository.missing_files("demo", repository.load("demo")) == ()


def test_missing_files_treats_a_directory_as_missing(products: Path) -> None:
    directory = _write_valid(products)
    (directory / "openapi.json").mkdir()
    repository = FileProfileRepository(products)

    assert len(repository.missing_files("demo", repository.load("demo"))) == 1


def test_missing_files_does_not_read_file_content(products: Path) -> None:
    directory = _write_valid(products)
    (directory / "openapi.json").write_bytes(b"\xff\xfe nao-e-utf8 " + SECRET.encode())
    repository = FileProfileRepository(products)

    assert repository.missing_files("demo", repository.load("demo")) == ()
