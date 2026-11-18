"""QA independente (V1.5c) do multipart sintético (ADR 0052): tetos, nomes, conteúdo e resumo."""

import itertools
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.multipart_encoding import encode_multipart, summarize_multipart
from harness_dast.domain.multipart_schema import plan_parts
from harness_dast.domain.synthetic_files import (
    FILE_KINDS,
    MAX_FILE_BYTES,
    MAX_MULTIPART_BYTES,
    MAX_PARTS,
    FileSpec,
    file_content,
    file_content_type,
    is_safe_name,
    kind_from_content_type,
    parse_file_spec,
    resolve_file,
    validate_file,
)

HOSTILE_NAMES = [
    "",
    ".",
    "..",
    "a..b.txt",
    "../etc/passwd.txt",
    "a/b.txt",
    "a\\b.txt",
    'a".txt',
    "a'.txt",
    "a\r\n.txt",
    "a\n.txt",
    "a.txt\n",
    "a.txt\x00",
    "a\x00.txt",
    " a.txt",
    "a b.txt",
    ".hidden.txt",
    "-rf.txt",
    "é.txt",
    "ａ.txt",  # noqa: RUF001 - letra de largura total, de propósito
    "a‮txt.txt",
    "a​.txt",
    "٣.txt",
    "a;b.txt",
    "a=b.txt",
    "%2e%2e.txt",
    "a" * 65 + ".txt",
    "a" * 70,
    "<script>.txt",
    "a$(id).txt",
    "a`id`.txt",
]


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_hostile_names_are_refused_by_every_entry_point(name: str) -> None:
    assert is_safe_name(name) is False
    with pytest.raises(ConfigError):
        validate_file("text", name)
    with pytest.raises(ConfigError):
        encode_multipart([(name, "x")], [])
    with pytest.raises(ConfigError):
        encode_multipart([], [FileSpec(field="f", kind="text", filename=name)])
    with pytest.raises(ConfigError):
        encode_multipart([], [FileSpec(field=name, kind="text", filename="s.txt")])


@pytest.mark.parametrize("name", [n for n in HOSTILE_NAMES if len(n) > 4])
def test_a_hostile_name_never_appears_in_the_error_message(name: str) -> None:
    with pytest.raises(ConfigError) as error:
        validate_file("text", name)

    assert name not in error.value.message
    assert name not in (error.value.hint or "")


@pytest.mark.parametrize("name", ["shell.php.txt", "a.html.txt", "run.sh.txt", "x.exe.png"])
def test_a_double_extension_keeps_the_extension_of_the_declared_kind(name: str) -> None:
    kind = "png" if name.endswith(".png") else "text"

    assert validate_file(kind, name) == (kind, name)


@pytest.mark.parametrize(
    ("kind", "name"),
    [("text", "a.exe"), ("png", "a.php"), ("csv", "a.txt"), ("json", "a.js"), ("text", "a.TXT.sh")],
)
def test_an_extension_that_does_not_match_the_kind_is_refused(kind: str, name: str) -> None:
    with pytest.raises(ConfigError):
        validate_file(kind, name)


@pytest.mark.parametrize("kind", ["exe", "php", "html", "svg", "pdf", "zip", "", "TEXT", "png "])
def test_a_kind_outside_the_closed_list_is_refused(kind: str) -> None:
    with pytest.raises(ConfigError):
        validate_file(kind, "a.txt")
    with pytest.raises(ConfigError):
        resolve_file(kind, None)
    with pytest.raises(ConfigError):
        parse_file_spec(f"{kind}:a.txt")


@pytest.mark.parametrize("text", ["", "text", "text:", ":a.txt", "text:a.txt:b", "\x00:x"])
def test_a_malformed_file_spec_text_is_refused(text: str) -> None:
    with pytest.raises(ConfigError):
        parse_file_spec(text)


@pytest.mark.parametrize("kind", FILE_KINDS)
def test_every_synthetic_file_is_small_inert_and_never_executable(kind: Any) -> None:
    data = file_content(kind)

    assert 0 < len(data) <= MAX_FILE_BYTES
    assert not data.startswith((b"MZ", b"\x7fELF", b"#!", b"<?php", b"PK\x03\x04", b"%PDF"))
    for risky in (b"<script", b"<?", b"<html", b"<svg", b"eval(", b"exec(", b"system("):
        assert risky not in data.lower()
    assert file_content_type(kind) in {"text/plain", "text/csv", "application/json", "image/png"}


def test_a_declared_content_type_outside_the_list_never_selects_a_kind() -> None:
    for declared in (
        "application/x-msdownload",
        "text/html",
        "image/svg+xml",
        "application/x-php",
        "application/pdf",
        "image/jpeg",
        "*/*",
        "",
        "image/png\x00",
        "../png",
    ):
        assert kind_from_content_type(declared) is None
    assert kind_from_content_type("IMAGE/PNG; charset=x") == "png"


def test_encode_refuses_more_than_the_part_cap_and_zero_parts() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([(f"c{i}", "x") for i in range(MAX_PARTS + 1)], [])
    with pytest.raises(ConfigError):
        encode_multipart([], [])
    content_type, body = encode_multipart([(f"c{i}", "x") for i in range(MAX_PARTS)], [])
    assert len(body) <= MAX_MULTIPART_BYTES
    assert content_type.startswith("multipart/form-data; boundary=")


def test_encode_refuses_a_body_over_the_total_cap_even_with_valid_pieces() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([("campo", "a" * (MAX_MULTIPART_BYTES + 1))], [])
    with pytest.raises(ConfigError):
        encode_multipart([(f"c{i}", "a" * 1000) for i in range(20)], [])


def test_encode_refuses_a_repeated_field_name_across_text_and_file() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([("a", "x")], [FileSpec(field="a", kind="text", filename="s.txt")])
    with pytest.raises(ConfigError):
        encode_multipart([("a", "x"), ("a", "y")], [])


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.text(max_size=300), min_size=1, max_size=5),
)
def test_arbitrary_field_values_round_trip_and_never_forge_parts(values: list[str]) -> None:
    fields = [(f"campo{index}", value) for index, value in enumerate(values)]
    try:
        content_type, body = encode_multipart(fields, [])
    except ConfigError:
        return

    summary = summarize_multipart(content_type, body)

    # Um valor com CRLF e "--" nunca vira uma parte a mais: o resumo é o dos campos dados.
    assert summary is None or [part.name for part in summary.parts] == [n for n, _ in fields]


def test_a_value_that_looks_like_a_part_header_does_not_create_a_part() -> None:
    forged = 'x\r\n--b\r\nContent-Disposition: form-data; name="evil"; filename="a.exe"\r\n\r\nMZ'
    content_type, body = encode_multipart([("a", forged)], [])

    summary = summarize_multipart(content_type, body)

    assert summary is not None
    assert [part.name for part in summary.parts] == ["a"]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"--x--",
        b"--x\r\n\r\n--x--",
        b"--x\r\nContent-Disposition: form-data\r\n\r\nv\r\n--x--\r\n",
        b'--x\r\nContent-Disposition: form-data; name="../a"\r\n\r\nv\r\n--x--\r\n',
        b'--x\r\nContent-Disposition: form-data; name="a"; filename="../a"\r\n\r\nv\r\n--x--\r\n',
        b"--x\r\n" + b"A" * 70_000 + b"\r\n--x--",
        b"\xff\xfe\x00" * 1000,
        (b'--x\r\nContent-Disposition: form-data; name="a"\r\n\r\nv\r\n' * 25) + b"--x--\r\n",
    ],
)
def test_summarizing_a_malformed_body_returns_none_or_a_safe_summary_and_never_raises(
    body: bytes,
) -> None:
    summary = summarize_multipart("multipart/form-data; boundary=x", body)

    if summary is not None:
        assert len(summary.parts) <= MAX_PARTS
        assert all(is_safe_name(part.name) for part in summary.parts)
        assert all(part.filename is None or is_safe_name(part.filename) for part in summary.parts)


@pytest.mark.parametrize(
    "content_type",
    [
        "",
        "multipart/form-data",
        "multipart/form-data; boundary=",
        "text/plain",
        "multipart/mixed;;;",
    ],
)
def test_summarizing_without_a_usable_boundary_never_raises(content_type: str) -> None:
    summarize_multipart(
        content_type, b'--x\r\nContent-Disposition: form-data; name="a"\r\n\r\nv\r\n--x--'
    )


def test_the_summary_never_carries_values_the_boundary_or_file_bytes() -> None:
    marker = "valor-secreto-xyz"
    content_type, body = encode_multipart(
        [("campo", marker)], [FileSpec(field="arq", kind="png", filename="foto.png")]
    )
    boundary = content_type.split("boundary=")[1]

    dumped = summarize_multipart(content_type, body)

    assert dumped is not None
    text = dumped.model_dump_json()
    assert marker not in text
    assert boundary not in text
    assert "PNG" not in text
    assert {part.kind for part in dumped.parts} == {"field", "file"}


def _object(**properties: Schema) -> Schema:
    return Schema(type="object", properties=properties, required=tuple(properties))


BINARY = Schema(type="string", format="binary")


def test_plan_parts_refuses_nested_ambiguous_and_oversized_schemas() -> None:
    refusing: list[Schema | None] = [
        None,
        Schema(type="object"),
        _object(x=Schema(type="object", properties={"y": Schema(type="string")})),
        _object(x=Schema(type="array", items=Schema(type="object"))),
        _object(x=Schema(type="integer", format="binary")),
        _object(**{"a b": Schema(type="string")}),
        _object(**{"é": Schema(type="string")}),
        _object(**{f"c{i}": Schema(type="string") for i in range(MAX_PARTS + 1)}),
    ]
    for schema in refusing:
        with pytest.raises(ConfigError):
            plan_parts(schema, {})


def test_format_byte_is_text_and_a_list_of_binaries_is_one_file() -> None:
    plans = plan_parts(
        _object(
            texto=Schema(type="string", format="byte"),
            varios=Schema(type="array", items=BINARY),
            um=BINARY,
        ),
        {},
    )

    assert [(plan.name, plan.is_file) for plan in plans] == [
        ("texto", False),
        ("varios", True),
        ("um", True),
    ]


@pytest.mark.parametrize(
    "declared",
    ["application/x-msdownload", "text/html", "image/svg+xml", "../x", "image/png\r\nX: y", ""],
)
def test_a_declared_part_type_without_synthetic_equivalent_is_reported_not_trusted(
    declared: str,
) -> None:
    (plan,) = plan_parts(_object(arq=BINARY), {"arq": declared})

    assert plan.declared_kind is None
    assert plan.is_file is True


def test_every_combination_of_kinds_encodes_inside_the_caps() -> None:
    for kinds in itertools.product(FILE_KINDS, repeat=3):
        specs = [
            FileSpec(field=f"f{i}", kind=kind, filename=f"s{i}.{ext}")  # type: ignore[arg-type]
            for i, (kind, ext) in enumerate(
                zip(kinds, ("txt", "csv", "json", "png")[: len(kinds)], strict=False)
            )
            if (kind, ext) in {("text", "txt"), ("csv", "csv"), ("json", "json"), ("png", "png")}
        ]
        if not specs:
            continue
        _, body = encode_multipart([], specs)
        assert len(body) <= MAX_MULTIPART_BYTES
