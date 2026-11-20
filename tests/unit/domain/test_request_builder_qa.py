"""Casos de precedência e limites da paginação."""

import pytest

from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.request_builder import RequestBuilder
from tests.unit.api_helpers import TAG, body_operation, builder, obj, rule, rules_from


def operation(schema: Schema) -> Operation:
    return Operation(
        operation_id="list",
        method="get",
        path="/items",
        parameters=(Parameter(name="size", location="query", value_schema=schema),),
    )


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        (Schema(type="integer", minimum=20, maximum=21), "20"),
        (Schema(type="integer", minimum=20, maximum=22, exclusive_minimum=True), "21"),
        (Schema(type="integer", minimum=1, maximum=10, exclusive_maximum=True), "9"),
        (
            Schema(
                type="integer",
                minimum=19,
                maximum=21,
                exclusive_minimum=True,
                exclusive_maximum=True,
            ),
            "20",
        ),
    ],
)
def test_limites_abertos_e_fechados_continuam_validos(schema: Schema, expected: str) -> None:
    assert dict(builder().build(operation(schema)).query)["size"] == expected


def test_enum_e_regra_explicita_precedem_paginacao() -> None:
    schema = Schema(type="integer", minimum=1, maximum=50, enum=(25, 30))
    op = operation(schema)
    assert dict(builder().build(op).query)["size"] == "25"
    rules = rules_from(rule("size", "constant", value=30))
    assert dict(builder(rules).build(op).query)["size"] == "30"


def test_campo_do_corpo_com_nome_size_nao_e_tratado_como_paginacao() -> None:
    schema = obj(("size",), size=Schema(type="integer", minimum=1, maximum=50))
    request = RequestBuilder(rules_from(), lambda _: 25, TAG).build(body_operation(schema))
    assert request.body == {"size": 25}
