"""Integração leve: OpenAPI real do VAmPI -> regras -> requisições para TODAS as operações."""

from pathlib import Path

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.openapi import load_spec
from harness_dast.domain.api_summary import summarize
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.request_builder import BuiltRequest, RequestBuilder
from tests.unit.api_helpers import NOW, TAG
from tests.unit.schema_oracle import conforms

VAMPI = Path(__file__).parents[3] / "fixtures" / "specs" / "vampi.yml"
RULES = {
    "schema_version": 1,
    "rules": [
        {"match": {"field": "username"}, "generator": "alphanumeric", "unique": True},
        {"match": {"field": "email"}, "generator": "email", "unique": True},
        {"match": {"field": "book_title"}, "generator": "alphanumeric", "unique": True},
    ],
}


def build_all(seed: int) -> list[BuiltRequest]:
    spec = load_spec(VAMPI)
    builder = RequestBuilder(DataRules.from_data(RULES), GeneratorCatalogue(seed, NOW), TAG)
    return [builder.build(operation) for operation in spec.operations]


def test_every_vampi_operation_gets_a_valid_request() -> None:
    spec = load_spec(VAMPI)

    built = build_all(1)

    assert len(built) == len(spec.operations) == 14
    for operation, request in zip(spec.operations, built, strict=True):
        assert request.operation_id == operation.operation_id
        assert "{" not in request.path
        body = operation.request_body
        if body is not None and body.media[0].body_schema is not None:
            assert conforms(body.media[0].body_schema, request.body)


def test_vampi_unique_rules_produce_values_that_never_repeat_inside_a_run() -> None:
    values = [
        r.body["username"]
        for r in build_all(1)
        if isinstance(r.body, dict) and "username" in r.body
    ]
    paths = [r.path for r in build_all(1)]

    assert len(values) == len(set(values)) >= 2
    assert any("7f3a" in path for path in paths)


def test_vampi_requests_are_reproducible_for_the_same_seed_and_differ_for_another() -> None:
    assert build_all(5) == build_all(5)
    assert build_all(5) != build_all(6)


def test_the_agent_summary_of_vampi_fits_its_budget() -> None:
    summary = summarize(load_spec(VAMPI), budget_chars=10_000)

    assert summary.omitted_operations == 0
    assert summary.operation_count == 14
    assert len(summary.model_dump_json()) <= 10_000
    by_id = {op.id: op for op in summary.operations}
    register = by_id["api_views.users.register_user"]
    assert register.method == "POST"
    assert register.optional_inputs == 3
    assert by_id["api_views.users.get_by_username"].inputs[0].where == "path"
    assert by_id["api_views.users.me"].auth
