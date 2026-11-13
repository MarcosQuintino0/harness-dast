"""Construtores pequenos usados pelos testes de API, regras e requisições."""

from datetime import UTC, datetime

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.domain.api_model import (
    HttpMethod,
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
    SuccessResponse,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.request_builder import RequestBuilder

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TAG = "7f3a"


def rules_from(*rules: dict[str, object]) -> DataRules:
    return DataRules.from_data({"schema_version": 1, "rules": list(rules)})


def rule(field: str, generator: str, *, unique: bool = False, **extra: object) -> dict[str, object]:
    match: dict[str, object] = {"field": field}
    for key in ("operation", "location"):
        if key in extra:
            match[key] = extra.pop(key)
    return {"match": match, "generator": generator, "unique": unique, "args": extra}


def builder(rules: DataRules | None = None, seed: int = 1) -> RequestBuilder:
    return RequestBuilder(rules or rules_from(), GeneratorCatalogue(seed, NOW), TAG)


def body_operation(
    schema: Schema,
    *,
    operation_id: str = "op",
    path: str = "/x",
    method: HttpMethod = "post",
    parameters: tuple[Parameter, ...] = (),
    responses: tuple[SuccessResponse, ...] = (),
) -> Operation:
    return Operation(
        operation_id=operation_id,
        method=method,
        path=path,
        parameters=parameters,
        request_body=RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
        success_responses=responses,
    )


def obj(required: tuple[str, ...] = (), **properties: Schema) -> Schema:
    return Schema(type="object", properties=properties, required=required)
