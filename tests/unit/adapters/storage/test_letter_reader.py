from pathlib import Path

import pytest

from harness_dast.adapters.storage.letter_reader import FileLetterReader
from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES
from harness_dast.domain.errors import ConfigError

SECRET = "SenhaLiteral-Nao-Pode-Vazar-9"  # noqa: S105 - sentinela para provar que não vaza


def _write(tmp_path: Path, content: str | bytes, name: str = "carta.yml") -> Path:
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def test_read_returns_the_map_when_the_letter_is_valid_yaml(tmp_path: Path) -> None:
    path = _write(tmp_path, "schema_version: 1\nproduct: demo\n")

    assert FileLetterReader().read(path) == {"schema_version": 1, "product": "demo"}


def test_read_accepts_a_utf8_bom(tmp_path: Path) -> None:
    path = _write(tmp_path, b"\xef\xbb\xbfschema_version: 1\n")

    assert FileLetterReader().read(path) == {"schema_version": 1}


def test_read_raises_when_the_file_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não foi encontrada"):
        FileLetterReader().read(tmp_path / "nao-existe.yml")


def test_read_raises_when_the_path_is_a_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        FileLetterReader().read(tmp_path)


def test_read_raises_when_the_file_is_too_big(tmp_path: Path) -> None:
    path = _write(tmp_path, "a: " + "x" * (MAX_PROFILE_BYTES + 10))

    with pytest.raises(ConfigError, match="grande demais"):
        FileLetterReader().read(path)


def test_read_raises_when_the_file_is_not_utf8(tmp_path: Path) -> None:
    path = _write(tmp_path, b"a: \xff\xfe\n")

    with pytest.raises(ConfigError, match="UTF-8"):
        FileLetterReader().read(path)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "- lista\n- na raiz\n",
        "a: [\n",
        "a: &x 1\nb: *x\n",
        "a: 1\na: 2\n",
        "base: &b {x: 1}\nother:\n  <<: *b\n",
        "a: !!binary aGk=\n",
    ],
)
def test_read_raises_for_an_empty_malformed_or_dangerous_document(
    tmp_path: Path, content: str
) -> None:
    path = _write(tmp_path, content)

    with pytest.raises(ConfigError):
        FileLetterReader().read(path)


def test_read_error_never_repeats_the_file_content(tmp_path: Path) -> None:
    path = _write(tmp_path, f"a: {SECRET}\na: {SECRET}\n")

    with pytest.raises(ConfigError) as caught:
        FileLetterReader().read(path)

    assert SECRET not in caught.value.message
    assert SECRET not in (caught.value.hint or "")
    assert "carta.yml" in caught.value.message
