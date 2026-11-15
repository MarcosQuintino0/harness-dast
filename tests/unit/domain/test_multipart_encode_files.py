"""`encode_multipart` e `summarize_multipart` (ADR 0052): campos, arquivos sintéticos e limites."""

from email import policy
from email.parser import BytesParser

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.multipart_encoding import encode_multipart, summarize_multipart
from harness_dast.domain.synthetic_files import FILE_KINDS, FileSpec, file_content


def parse(content_type: str, body: bytes):  # type: ignore[no-untyped-def]  # auxiliar de teste
    return BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )


def file_spec(field: str = "arquivo", kind: str = "text", name: str = "synthetic.txt") -> FileSpec:
    return FileSpec(field=field, kind=kind, filename=name)  # type: ignore[arg-type]


def test_encode_multipart_round_trips_fields_and_files_through_the_stdlib_parser() -> None:
    content_type, body = encode_multipart(
        [("descricao", "texto simples")],
        [file_spec("arquivo", "png", "foto.png"), file_spec("outro", "csv", "d.csv")],
    )

    message = parse(content_type, body)
    parts = list(message.iter_parts())
    assert not message.defects
    assert [p.get_param("name", header="content-disposition") for p in parts] == [
        "descricao",
        "arquivo",
        "outro",
    ]
    assert parts[0].get_payload(decode=True) == b"texto simples"
    assert parts[1].get_filename() == "foto.png"
    assert parts[1].get_content_type() == "image/png"
    assert parts[1].get_payload(decode=True) == file_content("png")
    assert parts[2].get_content_type() == "text/csv"
    assert not any(part.defects for part in parts)


def test_encode_multipart_is_deterministic_and_the_boundary_is_in_no_content() -> None:
    first = encode_multipart([("a", "x")], [file_spec()])

    assert first == encode_multipart([("a", "x")], [file_spec()])
    boundary = first[0].split("boundary=")[1].encode()
    assert first[1].count(b"--" + boundary) == 3
    assert all(boundary not in file_content(kind) for kind in FILE_KINDS)  # type: ignore[arg-type]


def test_a_field_value_equal_to_another_boundary_does_not_collide_with_its_own() -> None:
    _, body = encode_multipart([("a", "x")], [])
    other = body.split(b"\r\n", 1)[0][2:].decode()

    content_type, forged = encode_multipart([("a", other)], [])

    own = content_type.split("boundary=")[1]
    assert own != other
    assert forged.count(b"--" + own.encode()) == 2


@pytest.mark.parametrize("count", [21, 25])
def test_encode_multipart_refuses_more_than_twenty_parts(count: int) -> None:
    with pytest.raises(ConfigError):
        encode_multipart([(f"c{i}", "x") for i in range(count)], [])


def test_encode_multipart_accepts_exactly_twenty_parts() -> None:
    content_type, body = encode_multipart([(f"c{i}", "x") for i in range(19)], [file_spec()])

    assert len(list(parse(content_type, body).iter_parts())) == 20


def test_encode_multipart_refuses_no_parts() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([], [])


def test_encode_multipart_refuses_a_body_above_sixteen_kib() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([("a", "x" * 17_000)], [])


@pytest.mark.parametrize("name", ["", "a" * 65, "é", "n\r\nX: x", 'n"', "a b", "-a", "a/b", "a..b"])
def test_encode_multipart_refuses_unsafe_field_and_file_names(name: str) -> None:
    with pytest.raises(ConfigError):
        encode_multipart([(name, "x")], [])
    with pytest.raises(ConfigError):
        encode_multipart([], [file_spec(field=name)])
    with pytest.raises(ConfigError):
        encode_multipart([], [file_spec(name=name)])


def test_encode_multipart_refuses_repeated_names_across_fields_and_files() -> None:
    with pytest.raises(ConfigError):
        encode_multipart([("arquivo", "x")], [file_spec("arquivo")])
    with pytest.raises(ConfigError):
        encode_multipart([("a", "x"), ("a", "y")], [])


def test_summarize_multipart_reports_names_kinds_and_sizes_without_values() -> None:
    content_type, body = encode_multipart(
        [("d", "valor secreto")], [file_spec(kind="png", name="f.png")]
    )

    summary = summarize_multipart(content_type, body)

    assert summary is not None
    assert [(p.name, p.kind, p.filename, p.content_type, p.size) for p in summary.parts] == [
        ("d", "field", None, None, 13),
        ("arquivo", "file", "f.png", "image/png", 67),
    ]
    assert summary.total_bytes == 80
    dumped = summary.model_dump_json()
    assert "valor secreto" not in dumped
    assert "boundary" not in dumped


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("multipart/form-data; boundary=x", b"lixo"),
        ("multipart/form-data", b"--x\r\n\r\n"),
        ("text/plain", b"oi"),
        ("multipart/form-data; boundary=x", b""),
    ],
)
def test_summarize_multipart_returns_none_for_malformed_bodies(
    content_type: str, body: bytes
) -> None:
    assert summarize_multipart(content_type, body) is None


@settings(max_examples=60, deadline=None)
@given(
    names=st.lists(st.text(max_size=70), min_size=1, max_size=4, unique=True),
    value=st.text(max_size=40),
)
def test_for_any_field_names_the_result_is_refused_or_a_readable_multipart(
    names: list[str], value: str
) -> None:
    try:
        content_type, body = encode_multipart([(name, value) for name in names], [])
    except ConfigError:
        return

    summary = summarize_multipart(content_type, body)
    assert summary is not None
    assert [part.name for part in summary.parts] == names
