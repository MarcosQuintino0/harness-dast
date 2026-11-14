"""`summary` da operação do OpenAPI: nome simples para o painel (texto não confiável)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.api_model import Operation

OK = {"200": {"description": "ok"}}


def spec_with(tmp_path: Path, **operation: object):  # type: ignore[no-untyped-def]
    document = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {"/a": {"get": {"operationId": "a", "responses": OK, **operation}}},
    }
    path = tmp_path / "api.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_spec(path).operations[0]


def test_the_summary_is_read_and_trimmed(tmp_path: Path) -> None:
    assert spec_with(tmp_path, summary="  Ver   usuário  ").summary == "Ver usuário"


@pytest.mark.parametrize("value", [None, 5, ["x"], {"a": 1}, "", "   ", "\x00\x1f"])
def test_a_missing_or_malformed_summary_is_none(tmp_path: Path, value: object) -> None:
    operation = spec_with(tmp_path, summary=value) if value is not None else spec_with(tmp_path)

    assert operation.summary is None


def test_control_characters_in_the_summary_become_spaces(tmp_path: Path) -> None:
    assert spec_with(tmp_path, summary="a\nb\x1b[31mc").summary == "a b [31mc"


def test_a_very_long_summary_is_cut_to_two_hundred_characters(tmp_path: Path) -> None:
    summary = spec_with(tmp_path, summary="x" * 5000).summary

    assert summary is not None
    assert len(summary) == 200


def test_the_operation_model_refuses_a_summary_longer_than_two_hundred() -> None:
    with pytest.raises(ValidationError):
        Operation(operation_id="a", method="get", path="/a", summary="x" * 201)


def test_the_summary_is_optional_on_the_model() -> None:
    assert Operation(operation_id="a", method="get", path="/a").summary is None
