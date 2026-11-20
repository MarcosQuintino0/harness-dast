import json
from pathlib import Path

import pytest

from harness_dast.adapters.openapi import load_spec
from harness_dast.domain import api_summary
from harness_dast.domain.api_model import (
    MAX_MEDIA_TYPES,
    ApiSpec,
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
    SecurityRequirement,
    SuccessResponse,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.api_summary import (
    MAX_INPUTS_PER_OPERATION,
    MIN_BUDGET_CHARS,
    looks_like_identifier,
    summarize,
    summarize_operation,
)
from tests.unit.api_helpers import obj


@pytest.mark.parametrize(
    "name",
    ["id", "ID", "Id", "uuid", "user_id", "user-id", "pacienteId", "pacienteID", "x.id", "guid"],
)
def test_looks_like_identifier_accepts_common_id_names(name: str) -> None:
    assert looks_like_identifier(name, Schema())


@pytest.mark.parametrize("name", ["valid", "paid", "identity", "idade", "nome", "kid"])
def test_looks_like_identifier_rejects_words_that_merely_contain_id(name: str) -> None:
    assert not looks_like_identifier(name, Schema())


def test_looks_like_identifier_accepts_uuid_formatted_fields() -> None:
    assert looks_like_identifier("token", Schema(type="string", format="uuid"))


def create_patient() -> Operation:
    body = obj(
        ("nome", "endereco", "itens"),
        nome=Schema(type="string", min_length=3, max_length=20, pattern="^[A-Z]+$"),
        idade=Schema(type="integer", minimum=0, maximum=130),
        endereco=obj(("cep",), cep=Schema(type="string"), complemento=Schema(type="string")),
        itens=Schema(type="array", items=obj(("pacienteId",), pacienteId=Schema(type="integer"))),
        criado=Schema(type="string", read_only=True),
    )
    response = obj(id=Schema(type="integer"), dados=obj(uuid=Schema(type="string")))
    return Operation(
        operation_id="criar",
        method="post",
        path="/pacientes/{id}",
        parameters=(
            Parameter(
                name="id", location="path", required=True, value_schema=Schema(type="integer")
            ),
            Parameter(name="filtro", location="query"),
        ),
        request_body=RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=body),)
        ),
        success_responses=(SuccessResponse(status="201", body_schema=response),),
        security=(SecurityRequirement(schemes=("bearer",)),),
        deprecated=True,
    )


def test_summarize_operation_lists_required_inputs_with_type_and_constraints() -> None:
    summary = summarize_operation(create_patient())

    inputs = {(i.where, i.name): i for i in summary.inputs}
    assert inputs[("path", "id")].type == "integer"
    assert inputs[("body", "nome")].constraints == "len 3..20; pattern ^[A-Z]+$"
    assert inputs[("body", "endereco.cep")].type == "string"
    assert inputs[("body", "itens[].pacienteId")].type == "integer"
    assert summary.method == "POST"
    assert summary.auth
    assert summary.deprecated


def test_summarize_operation_counts_optional_inputs_without_listing_them() -> None:
    summary = summarize_operation(create_patient())

    assert summary.optional_inputs == 3  # filtro, idade, endereco.complemento (readOnly não conta)
    assert all(i.name not in {"idade", "filtro"} for i in summary.inputs)


def test_summarize_operation_flags_identifiers_produced_and_consumed() -> None:
    summary = summarize_operation(create_patient())

    assert summary.produces == ("id", "dados.uuid")
    assert summary.consumes == ("id", "itens[].pacienteId")


def test_summarize_operation_describes_enum_range_and_formats() -> None:
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(
            Parameter(
                name="tipo",
                location="query",
                required=True,
                value_schema=Schema(type="string", enum=tuple("abcdefgh")),
            ),
            Parameter(
                name="n",
                location="query",
                required=True,
                value_schema=Schema(type="integer", format="int64", minimum=1),
            ),
            Parameter(
                name="ids",
                location="query",
                required=True,
                value_schema=Schema(type="array", items=Schema(type="string", format="uuid")),
            ),
        ),
    )

    inputs = {i.name: i for i in summarize_operation(operation).inputs}

    assert inputs["tipo"].constraints == "enum a|b|c|d|e"
    assert (inputs["n"].type, inputs["n"].constraints) == ("integer/int64", "range 1..")
    assert inputs["ids"].type == "array<string/uuid>"


def test_summarize_operation_caps_the_number_of_listed_inputs() -> None:
    parameters = tuple(
        Parameter(name=f"p{i}", location="query", required=True)
        for i in range(MAX_INPUTS_PER_OPERATION + 5)
    )
    summary = summarize_operation(
        Operation(operation_id="a", method="get", path="/a", parameters=parameters)
    )

    assert len(summary.inputs) == MAX_INPUTS_PER_OPERATION
    assert summary.more_inputs == 5


def test_summarize_operation_cuts_long_texts_and_stops_at_the_depth_limit() -> None:
    deep: Schema = Schema(type="string")
    for _ in range(6):
        deep = obj(("x",), x=deep)
    operation = Operation(
        operation_id="o" * 200,
        method="post",
        path="/" + "p" * 300,
        request_body=RequestBody(
            media=(MediaBody(media_type="application/json", body_schema=deep),)
        ),
    )

    summary = summarize_operation(operation)

    assert len(summary.id) == 120
    assert summary.id.endswith("…")
    assert len(summary.path) == 120
    assert summary.inputs == ()


def small_spec(count: int) -> ApiSpec:
    operations = tuple(
        Operation(
            operation_id=f"op{i}",
            method="post",
            path=f"/r{i}",
            parameters=tuple(
                Parameter(name=f"campo{j}", location="query", required=True) for j in range(10)
            ),
        )
        for i in range(count)
    )
    return ApiSpec(title="T" * 200, version="1", operations=operations)


def test_summarize_keeps_everything_when_it_fits_the_budget() -> None:
    summary = summarize(small_spec(3))

    assert summary.operation_count == 3
    assert summary.omitted_operations == 0
    assert len(summary.title) == 60


def test_summarize_never_exceeds_the_budget_and_counts_the_omitted_operations() -> None:
    spec = small_spec(2000)

    summary = summarize(spec, budget_chars=20_000)

    assert len(summary.model_dump_json()) <= 20_000
    assert summary.omitted_operations > 0
    assert len(summary.operations) + summary.omitted_operations == 2000
    assert summary.operations[0].id == "op0"


def test_summarize_enforces_a_minimum_budget() -> None:
    summary = summarize(small_spec(500), budget_chars=10)

    assert len(summary.model_dump_json()) <= MIN_BUDGET_CHARS


def test_summarize_is_deterministic() -> None:
    assert summarize(small_spec(50), 5_000) == summarize(small_spec(50), 5_000)


def test_summary_detects_multipart_even_when_json_is_preferred() -> None:
    operation = Operation(
        operation_id="upload",
        method="post",
        path="/upload",
        request_body=RequestBody(
            media=(
                MediaBody(media_type="application/json"),
                MediaBody(media_type=" Multipart/Form-Data ; charset=utf-8"),
            )
        ),
    )

    result = summarize_operation(operation)

    assert result.multipart_offline is True
    assert result.model_dump()["multipart_offline"] is True


def test_summary_marks_absent_multipart_as_none() -> None:
    result = summarize_operation(create_patient())
    assert result.multipart_offline is None
    assert "multipart_offline" not in result.model_dump()
    assert (
        summarize_operation(Operation(operation_id="a", method="get", path="/a")).multipart_offline
        is None
    )


def test_summary_runs_multipart_proof_once_for_multiple_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def verify() -> bool:
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(api_summary, "verify_synthetic_multipart", verify)
    media = RequestBody(media=(MediaBody(media_type="multipart/form-data"),))
    spec = ApiSpec(
        title="A",
        version="1",
        operations=tuple(
            Operation(operation_id=f"op{i}", method="post", path=f"/{i}", request_body=media)
            for i in range(3)
        ),
    )

    summary = summarize(spec)

    assert calls == 1
    assert [item.multipart_offline for item in summary.operations] == [False, False, False]
    assert all(item.model_dump()["multipart_offline"] is False for item in summary.operations)


def load_media_summary(
    tmp_path: Path, media_types: list[str]
) -> tuple[Operation, dict[str, object]]:
    content: dict[str, dict[str, object]] = {name: {} for name in media_types}
    document = {
        "openapi": "3.0.0",
        "info": {"title": "Teste", "version": "1"},
        "paths": {
            "/upload": {
                "post": {
                    "operationId": "upload",
                    "requestBody": {"content": content},
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    operation = load_spec(path).operations[0]
    return operation, summarize_operation(operation).model_dump()


@pytest.mark.parametrize(
    ("position", "detected", "incomplete"),
    [(20, True, False), (21, True, False), (100, True, False), (101, False, True)],
)
def test_summary_inspects_bounded_media_keys_without_changing_preferred_media(
    tmp_path: Path, position: int, detected: bool, incomplete: bool
) -> None:
    media = ["application/json", *(f"application/x-{i}" for i in range(1, position - 1))]
    media.append("multipart/form-data")

    operation, summary = load_media_summary(tmp_path, media)

    assert "multipart/form-data" in media
    assert operation.request_body is not None
    assert len(operation.request_body.media) == MAX_MEDIA_TYPES
    assert "multipart_declared" not in operation.request_body.model_dump()
    assert "multipart_inspection_incomplete" not in operation.request_body.model_dump()
    preferred = operation.request_body.preferred()
    assert preferred is not None
    assert preferred == operation.request_body.media[0]
    assert preferred.media_type == "application/json"
    assert summary.get("multipart_offline") is (True if detected else None)
    assert summary.get("multipart_inspection_incomplete", False) is incomplete


def test_summary_keeps_a_positive_multipart_result_when_some_keys_are_unchecked(
    tmp_path: Path,
) -> None:
    media = ["multipart/form-data", *(f"application/x-{i}" for i in range(100))]

    _, summary = load_media_summary(tmp_path, media)

    assert summary["multipart_offline"] is True
    assert summary["multipart_inspection_incomplete"] is True


@pytest.mark.parametrize(
    "name", [" " * 100 + "multipart/form-data", "multipart/form-data" + " " * 100 + "x"]
)
def test_summary_does_not_assert_multipart_for_an_unchecked_long_key(
    tmp_path: Path, name: str
) -> None:
    _, summary = load_media_summary(tmp_path, [name])

    assert "multipart_offline" not in summary
    assert summary["multipart_inspection_incomplete"] is True


def test_summary_reports_non_string_media_keys_as_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        "openapi: 3.0.0\n"
        "paths:\n"
        "  /upload:\n"
        "    post:\n"
        "      requestBody:\n"
        "        content:\n"
        "          123: {}\n"
        "      responses:\n"
        "        '200': {description: ok}\n",
        encoding="utf-8",
    )

    summary = summarize_operation(load_spec(path).operations[0]).model_dump()

    assert "multipart_offline" not in summary
    assert summary["multipart_inspection_incomplete"] is True
