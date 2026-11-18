"""Testes independentes dos diagnósticos offline da V1.5."""

import json
from pathlib import Path

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.api_summary import summarize
from harness_dast.domain.spec_examples import inspect_examples
from tests.fakes.rig import operation


def test_null_example_must_obey_enum_even_when_nullable() -> None:
    schema = Schema(type="string", nullable=True, enum=("allowed",), declared_examples=(None,))
    spec = ApiSpec(
        title="T",
        version="1",
        operations=(operation("criar", "post", "/api", body={"dados": schema}),),
    )

    assert any(code == "enum" for _, code in inspect_examples(spec))


def test_multipart_after_twenty_media_types_is_still_reported(tmp_path: Path) -> None:
    content: dict[str, dict[str, object]] = {f"application/x-{i}": {} for i in range(20)}
    content["multipart/form-data"] = {}
    document = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {"/upload": {"post": {"requestBody": {"content": content}, "responses": {}}}},
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert summarize(load_spec(path)).operations[0].multipart_offline is True


def test_local_nullable_enum_distinguishes_null_membership(tmp_path: Path) -> None:
    content = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/api": {
                "post": {
                    "parameters": [
                        {
                            "name": name,
                            "in": "query",
                            "schema": {"type": "string", "nullable": True, "enum": enum},
                            "example": None,
                        }
                        for name, enum in (("allowed", ["x", None]), ("rejected", ["x"]))
                    ],
                    "responses": {},
                }
            }
        },
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(content), encoding="utf-8")

    issues = inspect_examples(load_spec(path))

    assert len(issues) == 1
    assert "rejected" in issues[0][0]
    assert issues[0][1] == "enum"
