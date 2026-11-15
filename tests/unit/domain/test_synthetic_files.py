"""Arquivos sintéticos de lista fechada (ADR 0052): conteúdo, tipo, nome e limites."""

import struct
import zlib

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.synthetic_files import (
    FILE_KINDS,
    MAX_FILE_BYTES,
    default_filename,
    file_content,
    file_content_type,
    is_safe_name,
    kind_from_content_type,
    parse_file_spec,
    resolve_file,
    validate_file,
)

EXPECTED = {
    "text": (b"synthetic file\n", "text/plain", ".txt"),
    "csv": (b"id,value\n1,synthetic\n", "text/csv", ".csv"),
    "json": (b'{"synthetic":true}\n', "application/json", ".json"),
}


@pytest.mark.parametrize("kind", sorted(EXPECTED))
def test_each_text_kind_has_the_fixed_content_type_and_extension(kind: str) -> None:
    content, content_type, extension = EXPECTED[kind]

    assert file_content(kind) == content  # type: ignore[arg-type]  # parametrizado
    assert file_content_type(kind) == content_type  # type: ignore[arg-type]
    assert default_filename(kind).endswith(extension)  # type: ignore[arg-type]


def test_the_closed_list_has_exactly_four_kinds() -> None:
    assert set(FILE_KINDS) == {"text", "csv", "json", "png"}


def test_every_file_is_at_most_one_kib() -> None:
    assert all(len(file_content(kind)) <= MAX_FILE_BYTES for kind in FILE_KINDS)  # type: ignore[arg-type]


def test_the_png_has_a_valid_signature_and_valid_chunk_checksums() -> None:
    data = file_content("png")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, names = 8, []
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        name = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(">I", data[position + 8 + length : position + 12 + length])
        assert zlib.crc32(name + payload) & 0xFFFFFFFF == crc
        names.append(name)
        position += 12 + length
    assert position == len(data)
    assert names == [b"IHDR", b"IDAT", b"IEND"]
    assert len(data) == 67


@pytest.mark.parametrize("kind", FILE_KINDS)
def test_no_file_looks_executable_or_active_content(kind: str) -> None:
    data = file_content(kind)  # type: ignore[arg-type]

    for start in (b"MZ", b"\x7fELF", b"#!", b"<?", b"PK", b"%PDF", b"<"):
        assert not data.startswith(start)
    assert b"<script" not in data.lower()
    assert b"<" not in data
    assert kind != "text" or b";" not in data


@pytest.mark.parametrize(
    ("declared", "kind"),
    [
        ("image/png", "png"),
        ("text/csv", "csv"),
        ("application/json", "json"),
        ("text/plain", "text"),
        ("IMAGE/PNG; charset=x", "png"),
    ],
)
def test_declared_content_types_with_a_synthetic_kind_are_mapped(declared: str, kind: str) -> None:
    assert kind_from_content_type(declared) == kind


@pytest.mark.parametrize(
    "declared",
    [None, "", "image/jpeg", "video/mp4", "application/pdf", "application/octet-stream", "x"],
)
def test_declared_content_types_without_a_synthetic_kind_are_not_mapped(
    declared: str | None,
) -> None:
    assert kind_from_content_type(declared) is None


def test_parse_file_spec_accepts_kind_and_name() -> None:
    assert parse_file_spec("png:foto.png") == ("png", "foto.png")
    assert parse_file_spec("text:a_b-c.TXT") == ("text", "a_b-c.TXT")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "png",
        "exe:foto.exe",
        "png:foto.txt",
        "png:",
        "png:a/b.png",
        "png:a\\b.png",
        "png:..a.png",
        "png:a..b.png",
        'png:a".png',
        "png:a\r\nX: y.png",
        "png:a\n.png",
        "png:" + "a" * 61 + ".png",
        "png:fôto.png",
        "png:\u0661.png",
        "png:.png",
        "png: foto.png",
    ],
)
def test_parse_file_spec_refuses_unknown_kind_and_hostile_names(text: str) -> None:
    with pytest.raises(ConfigError):
        parse_file_spec(text)


def test_a_name_of_exactly_64_characters_is_accepted_and_65_is_not() -> None:
    assert is_safe_name("a" * 64)
    assert not is_safe_name("a" * 65)
    assert not is_safe_name("")


def test_resolve_file_uses_the_default_name_when_none_is_given() -> None:
    assert resolve_file("png", None) == ("png", "synthetic.png")
    assert resolve_file("csv", "dados.csv") == ("csv", "dados.csv")


def test_resolve_file_refuses_an_unknown_kind_even_without_a_name() -> None:
    with pytest.raises(ConfigError):
        resolve_file("svg", None)


def test_the_error_message_never_repeats_the_hostile_value() -> None:
    with pytest.raises(ConfigError) as info:
        validate_file("png", "evil\r\nInjected: 1.png")

    assert "Injected" not in info.value.message
