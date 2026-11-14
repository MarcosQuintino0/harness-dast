"""Prova do formato multipart sintético, sem servidor ou arquivos."""

from email import policy
from email.parser import BytesParser

import pytest

from harness_dast.domain import multipart_encoding
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.multipart_encoding import (
    encode_synthetic_multipart,
    verify_synthetic_multipart,
)


def test_synthetic_multipart_round_trips_through_stdlib_parser() -> None:
    content_type, body = encode_synthetic_multipart("descricao", "arquivo")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )

    assert not message.defects
    parts = list(message.iter_parts())
    assert len(parts) == 2
    assert parts[0].get_param("name", header="content-disposition") == "descricao"
    assert parts[0].get_payload(decode=True) == b"synthetic"
    assert parts[1].get_param("name", header="content-disposition") == "arquivo"
    assert parts[1].get_filename() == "synthetic.txt"
    assert parts[1].get_content_type() == "text/plain"
    assert parts[1].get_payload(decode=True) == b"synthetic file\n"
    assert not any(part.defects for part in parts)
    assert len(body) < 1024


def test_synthetic_multipart_is_deterministic_and_boundary_is_not_in_contents() -> None:
    content_type, body = encode_synthetic_multipart("field", "file")

    assert (content_type, body) == encode_synthetic_multipart("field", "file")
    boundary = content_type.split("boundary=")[1].encode()
    assert len(boundary) == 70
    assert boundary not in b"synthetic"
    assert boundary not in b"synthetic file\n"
    assert body.count(b"--" + boundary) == 3
    assert verify_synthetic_multipart()


@pytest.mark.parametrize("name", ["", "a" * 65, "é", "nome\r\nX: x", 'nome"', "a b", "-a"])
def test_synthetic_multipart_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ConfigError):
        encode_synthetic_multipart(name, "file")
    with pytest.raises(ConfigError):
        encode_synthetic_multipart("field", name)


def test_synthetic_multipart_rejects_duplicate_names() -> None:
    with pytest.raises(ConfigError):
        encode_synthetic_multipart("same", "same")


def test_synthetic_multipart_accepts_maximum_name_length() -> None:
    _, body = encode_synthetic_multipart("a" * 64, "file")

    assert len(body) < 1024


def test_verification_reports_failure_for_malformed_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        multipart_encoding,
        "encode_synthetic_multipart",
        lambda _field, _file: ("multipart/form-data; boundary=missing", b"invalid"),
    )

    assert not verify_synthetic_multipart()
