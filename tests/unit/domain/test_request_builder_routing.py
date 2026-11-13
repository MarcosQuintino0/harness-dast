"""O montador pula cabeçalho de roteamento do OpenAPI e diz por quê em `skipped_fields`."""

from datetime import UTC, datetime

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.request_builder import RequestBuilder

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def test_build_skips_routing_headers_with_a_reason_and_keeps_the_others() -> None:
    operation = Operation(
        operation_id="a",
        method="get",
        path="/a",
        parameters=(
            Parameter(
                name="Host", location="header", required=True, value_schema=Schema(type="string")
            ),
            Parameter(
                name="X-Trace", location="header", required=True, value_schema=Schema(type="string")
            ),
        ),
    )
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {"match": {"field": "Host"}, "generator": "constant", "args": {"value": "x"}},
                {"match": {"field": "X-Trace"}, "generator": "constant", "args": {"value": "t"}},
            ],
        }
    )

    built = RequestBuilder(rules, GeneratorCatalogue(1, NOW), "7f3a").build(operation)

    assert built.headers == {"X-Trace": "t"}
    assert any("Host" in item and "roteamento" in item for item in built.skipped_fields)
