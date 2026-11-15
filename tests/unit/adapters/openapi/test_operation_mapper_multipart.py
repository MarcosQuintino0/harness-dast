"""`encoding.<campo>.contentType` do multipart no carregador do OpenAPI (ADR 0052)."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.api_model import MediaBody
from harness_dast.domain.api_summary import summarize_operation

BINARY = {"type": "string", "format": "binary"}


def media_of(tmp_path: Path, content: dict[str, object]) -> MediaBody:
    document = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/up": {
                "post": {
                    "operationId": "up",
                    "requestBody": {"content": content},
                    "responses": {"201": {"description": "ok"}},
                }
            }
        },
    }
    path = tmp_path / "api.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    body = load_spec(path).operations[0].request_body
    assert body is not None
    return body.media[0]


def multipart(encoding: object = None, extra: dict[str, object] | None = None) -> dict[str, object]:
    media: dict[str, object] = {
        "schema": {"type": "object", "properties": {"arquivo": BINARY, "foto": BINARY}}
    }
    if encoding is not None:
        media["encoding"] = encoding
    return {"multipart/form-data": media | (extra or {})}


def test_the_declared_content_type_of_each_field_is_read(tmp_path: Path) -> None:
    media = media_of(
        tmp_path,
        multipart({"arquivo": {"contentType": "image/png"}, "foto": {"contentType": "text/csv"}}),
    )

    assert media.part_content_types == {"arquivo": "image/png", "foto": "text/csv"}


def test_a_document_without_encoding_has_no_part_types(tmp_path: Path) -> None:
    assert media_of(tmp_path, multipart()).part_content_types == {}


def test_only_the_first_type_of_a_list_is_kept_in_lowercase_without_parameters(
    tmp_path: Path,
) -> None:
    media = media_of(
        tmp_path, multipart({"arquivo": {"contentType": "IMAGE/PNG; charset=x, image/jpeg"}})
    )

    assert media.part_content_types == {"arquivo": "image/png"}


@pytest.mark.parametrize(
    "encoding",
    [
        "texto",
        ["a"],
        42,
        {"arquivo": "image/png"},
        {"arquivo": {"contentType": 5}},
        {"arquivo": {"contentType": ["image/png"]}},
        {"arquivo": {"contentType": ""}},
        {"arquivo": {"contentType": "nao-e-um-tipo"}},
        {"arquivo": {"contentType": "image/png\r\nX: y"}},
        {"arquivo": {"contentType": "a/" + "b" * 200}},
        {"a" * 80: {"contentType": "image/png"}},
        {"arquivo": None},
    ],
)
def test_malformed_encoding_is_ignored_and_never_breaks_the_load(
    tmp_path: Path, encoding: object
) -> None:
    media = media_of(tmp_path, multipart(encoding))

    assert media.part_content_types == {}


def test_the_number_of_stored_types_is_limited(tmp_path: Path) -> None:
    encoding = {f"c{i}": {"contentType": "image/png"} for i in range(80)}

    media = media_of(tmp_path, multipart(encoding))

    assert len(media.part_content_types) == 50


def test_encoding_of_a_non_multipart_media_is_ignored(tmp_path: Path) -> None:
    content: dict[str, object] = {
        "application/json": {
            "schema": {"type": "object"},
            "encoding": {"arquivo": {"contentType": "image/png"}},
        }
    }

    assert media_of(tmp_path, content).part_content_types == {}


def test_the_probe_readiness_is_ready_for_a_file_schema_and_unsupported_for_nested(
    tmp_path: Path,
) -> None:
    ready = media_of(tmp_path, multipart())
    assert ready.body_schema is not None
    document = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/a": {
                "post": {
                    "operationId": "a",
                    "requestBody": {"content": multipart()},
                    "responses": {"201": {"description": "ok"}},
                }
            },
            "/b": {
                "post": {
                    "operationId": "b",
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"x": {"type": "object"}},
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "ok"}},
                }
            },
        },
    }
    path = tmp_path / "two.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    first, second = load_spec(path).operations

    assert summarize_operation(first).multipart_probe == "ready"
    assert summarize_operation(second).multipart_probe == "unsupported_schema"
