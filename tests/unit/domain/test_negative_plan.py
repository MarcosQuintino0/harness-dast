"""Plano do teste negativo: o que mexer, em que ordem e o que fica sem teste (ADR 0051)."""

import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, Parameter, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.multipart_encoding import MultipartPart, MultipartSummary
from harness_dast.domain.negative_config import NegativeConfig
from harness_dast.domain.negative_plan import NegativeCase, NegativePlan, plan_negative
from harness_dast.domain.negative_request import render_case
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.negative_rig import (
    ADJUST,
    CREATE,
    LIST,
    REMOVE,
    UPDATE,
    catalog_spec,
    exchange,
)

SPEC = catalog_spec()
OPERATIONS = {operation.operation_id: operation for operation in SPEC.operations}
WRITES = NegativeConfig(allow_writes=True)


def plan(
    *exchanges: ExchangeRecord,
    config: NegativeConfig | None = None,
    operations: dict[str, Operation] | None = None,
    **kwargs: Any,
) -> NegativePlan:
    kwargs.setdefault("max_requests", 1000)
    return plan_negative(exchanges, operations or OPERATIONS, config or NegativeConfig(), **kwargs)


def names(result: NegativePlan) -> list[tuple[str, str, str]]:
    return [(c.exchange.operation_id, c.field, c.case_class) for c in result.cases]


def reasons(result: NegativePlan) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for note in result.not_tested:
        found.setdefault(note.operation_id or "", []).append(note.reason)
    return found


def operation_with(body: dict[str, Schema], *, required: tuple[str, ...] = ()) -> Operation:
    schema = Schema(type="object", properties=body, required=required)
    return Operation(
        operation_id="op",
        method="post",
        path="/api/x",
        request_body=RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
        ),
    )


def test_a_read_plans_one_case_per_field_in_priority_rounds() -> None:
    result = plan(LIST)

    assert names(result)[:3] == [
        ("listarProdutos", "limite", "wrong_type"),
        ("listarProdutos", "ordem", "not_in_enum"),
        ("listarProdutos", "busca", "too_long"),
    ]
    assert ("listarProdutos", "limite", "below_minimum") in names(result)
    assert ("listarProdutos", "limite", "above_maximum") in names(result)


def test_the_plan_is_deterministic() -> None:
    first = plan(LIST, CREATE, UPDATE, ADJUST, config=WRITES)
    second = plan(LIST, CREATE, UPDATE, ADJUST, config=WRITES)

    assert names(first) == names(second)
    assert first.not_tested == second.not_tested


def test_reads_come_before_writes_and_operations_take_turns() -> None:
    result = plan(CREATE, LIST, UPDATE, config=WRITES)

    methods = [c.exchange.method for c in result.cases]
    assert methods.index("POST") > max(i for i, m in enumerate(methods) if m == "GET")
    writes = [c.exchange.operation_id for c in result.cases if c.exchange.method != "GET"]
    assert writes[:2] == ["criarProduto", "atualizarProduto"]


def test_each_request_changes_exactly_one_field_of_the_proven_one() -> None:
    result = plan(LIST, CREATE, UPDATE, ADJUST, config=WRITES)

    for case in result.cases:
        target, body = render_case(case)
        base = case.exchange
        if case.location == "query":
            before = dict(parse_qsl(urlsplit(base.target).query))
            after = dict(parse_qsl(urlsplit(target).query))
            assert body == base.body
            changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        else:
            before_body = json.loads(base.body or "{}")
            after_body = json.loads(body or "{}")
            assert target == base.target
            changed = {
                k
                for k in before_body.keys() | after_body.keys()
                if before_body.get(k) != after_body.get(k)
            }
        assert changed == {case.field}


def test_missing_required_removes_the_field_and_is_never_planned_for_patch() -> None:
    result = plan(CREATE, UPDATE, ADJUST, config=WRITES)

    removed = [c for c in result.cases if c.case_class == "missing_required"]
    assert {(c.exchange.operation_id, c.field) for c in removed} == {
        ("criarProduto", "nome"),
        ("criarProduto", "preco"),
        ("atualizarProduto", "nome"),
        ("atualizarProduto", "preco"),
    }
    _, body = render_case(removed[0])
    assert removed[0].field not in json.loads(body or "{}")
    assert all(
        c.case_class != "missing_required" for c in result.cases if c.exchange.method == "PATCH"
    )


def test_a_required_query_parameter_can_be_removed() -> None:
    operation = Operation(
        operation_id="listar",
        method="get",
        path="/api/x",
        parameters=(
            Parameter(
                name="q",
                location="query",
                required=True,
                value_schema=Schema(type="string", max_length=3),
            ),
        ),
    )
    read = exchange("listar", "GET", "/api/x", "/api/x?q=ab&outra=1")

    result = plan(read, operations={"listar": operation})

    removal = next(c for c in result.cases if c.case_class == "missing_required")
    assert render_case(removal)[0] == "/api/x?outra=1"


def test_writes_without_the_letter_are_not_planned_and_nothing_is_sent_for_them() -> None:
    result = plan(CREATE, UPDATE, ADJUST)

    assert result.cases == ()
    assert reasons(result) == {
        "criarProduto": ["writes_not_authorized"],
        "atualizarProduto": ["writes_not_authorized"],
        "ajustarProduto": ["writes_not_authorized"],
    }
    assert "negative.allow_writes" in result.not_tested[0].message


def test_a_delete_exchange_is_dropped_without_a_case() -> None:
    result = plan(REMOVE, LIST, config=WRITES)

    assert all(c.exchange.method != "DELETE" for c in result.cases)
    assert "removerProduto" not in reasons(result)


def test_the_domain_refuses_a_delete_case() -> None:
    with pytest.raises(ConfigError, match="DELETE nunca"):
        NegativeCase(REMOVE, "query", "x", "wrong_type", "type integer", "not-a-number")


def test_a_case_never_shows_the_value_in_repr_or_str() -> None:
    result = plan(LIST)

    for case in result.cases:
        assert "not-a-number" not in repr(case)
        assert "not-in-enum" not in str(case)
        assert str(case.value) not in repr(case) or str(case.value) in {"", "0", "101"}


def test_secret_named_omitted_and_read_only_fields_are_never_touched() -> None:
    operation = operation_with(
        {
            "senha": Schema(type="string", max_length=3),
            "token": Schema(type="string", max_length=3),
            "omitido": Schema(type="string", max_length=3),
            "leitura": Schema(type="string", max_length=3, read_only=True),
            "normal": Schema(type="string", max_length=3),
        }
    )
    base = exchange(
        "op",
        "POST",
        "/api/x",
        "/api/x",
        body={"senha": "a", "token": "b", "omitido": "c", "leitura": "d", "normal": "e"},
        omitted=("omitido",),
    )

    result = plan(base, config=WRITES, operations={"op": operation})

    assert {c.field for c in result.cases} == {"normal"}


def test_the_login_username_field_is_protected_in_put_and_patch_but_not_in_post() -> None:
    put = exchange(
        "atualizarProduto",
        "PUT",
        "/api/produtos/{id}",
        "/api/produtos/1",
        body={"nome": "x", "preco": 1},
    )
    post = exchange(
        "criarProduto", "POST", "/api/produtos", "/api/produtos", body={"nome": "x", "preco": 1}
    )

    result = plan(put, post, config=WRITES, username_field="nome")

    touched = {(c.exchange.method, c.field) for c in result.cases}
    assert ("PUT", "nome") not in touched
    assert ("PUT", "preco") in touched
    assert ("POST", "nome") in touched


def test_a_field_that_is_not_in_the_proven_body_is_never_invented() -> None:
    partial = exchange("criarProduto", "POST", "/api/produtos", "/api/produtos", body={"nome": "x"})

    result = plan(partial, config=WRITES)

    assert {c.field for c in result.cases} == {"nome"}


def test_a_repeated_query_parameter_is_skipped() -> None:
    read = exchange(
        "listarProdutos", "GET", "/api/produtos", "/api/produtos?limite=1&limite=2&ordem=asc"
    )

    result = plan(read)

    assert {c.field for c in result.cases} == {"ordem"}


def test_a_path_parameter_and_unknown_query_parameter_are_never_touched() -> None:
    read = exchange(
        "listarProdutos", "GET", "/api/produtos", "/api/produtos?desconhecido=1&limite=3"
    )

    result = plan(read)

    assert {c.field for c in result.cases} == {"limite"}


@pytest.mark.parametrize(
    "body",
    [None, "[1,2]", '"texto"', "42", "{quebrado", "null"],
)
def test_a_write_without_a_json_object_body_is_unsupported(body: str | None) -> None:
    broken = ExchangeRecord(
        operation_id="criarProduto",
        method="POST",
        path="/api/produtos",
        target="/api/produtos",
        account="adm",
        status=201,
        content_type=None if body is None else "application/json",
        body=body,
    )

    result = plan(broken, config=WRITES)

    assert result.cases == ()
    assert reasons(result) == {"criarProduto": ["unsupported_body"]}


def test_a_multipart_exchange_is_unsupported_and_never_planned() -> None:
    base = ExchangeRecord(
        operation_id="criarProduto",
        method="POST",
        path="/api/produtos",
        target="/api/produtos",
        account="adm",
        status=201,
        multipart=MultipartSummary(
            parts=(
                MultipartPart(
                    name="arquivo", kind="file", filename="a.txt", content_type="text/plain", size=4
                ),
            ),
            total_bytes=4,
        ),
    )

    result = plan(base, config=WRITES)

    assert result.cases == ()
    assert reasons(result) == {"criarProduto": ["unsupported_body"]}


def test_an_exchange_whose_operation_is_gone_is_reported() -> None:
    result = plan(exchange("sumiu", "GET", "/api/sumiu", "/api/sumiu?a=1"))

    assert reasons(result) == {"sumiu": ["operation_not_found"]}


def test_an_operation_without_declared_limits_says_there_is_no_testable_field() -> None:
    free = operation_with({"nome": Schema(type="object")})
    base = exchange("op", "POST", "/api/x", "/api/x", body={"nome": "x"})

    result = plan(base, config=WRITES, operations={"op": free})

    assert result.cases == ()
    assert reasons(result)["op"] == ["no_testable_field"]


def test_a_composite_field_is_skipped_and_a_contradictory_all_of_does_not_crash() -> None:
    operation = operation_with(
        {
            "escolha": Schema(one_of=(Schema(type="integer", minimum=1), Schema(type="string"))),
            "mistura": Schema(
                all_of=(Schema(type="integer", minimum=1), Schema(type="string", max_length=2))
            ),
            "normal": Schema(type="integer", minimum=1),
        }
    )
    base = exchange(
        "op", "POST", "/api/x", "/api/x", body={"escolha": 1, "mistura": 1, "normal": 2}
    )

    result = plan(base, config=WRITES, operations={"op": operation})

    assert {c.field for c in result.cases} == {"normal"}


def test_a_truncated_schema_node_is_skipped() -> None:
    operation = operation_with({"fundo": Schema(type="integer", minimum=1, truncated=True)})
    base = exchange("op", "POST", "/api/x", "/api/x", body={"fundo": 3})

    assert plan(base, config=WRITES, operations={"op": operation}).cases == ()


def test_the_budget_per_operation_cuts_the_extra_cases_and_reports_them() -> None:
    result = plan(LIST, config=NegativeConfig(max_cases_per_operation=2))

    assert len(result.cases) == 2
    cut = [n for n in result.not_tested if n.reason == "budget"]
    assert len(cut) == 1
    assert "max_cases_per_operation" in cut[0].message


def test_the_total_budget_cuts_what_is_left_and_reports_it_per_operation() -> None:
    result = plan(LIST, CREATE, config=WRITES, max_requests=4)

    assert len(result.cases) == 4
    cut = [n for n in result.not_tested if n.reason == "budget"]
    assert cut
    assert any("negative.max_requests" in n.message for n in cut)


def test_a_disabled_class_is_never_planned() -> None:
    config = NegativeConfig(allow_writes=True, disabled_classes=("wrong_type", "missing_required"))

    result = plan(LIST, CREATE, config=config)

    assert {c.case_class for c in result.cases}.isdisjoint({"wrong_type", "missing_required"})


def test_only_keeps_the_chosen_operations() -> None:
    result = plan(LIST, CREATE, config=WRITES, only=frozenset({"criarProduto"}))

    assert {c.exchange.operation_id for c in result.cases} == {"criarProduto"}


def test_a_case_without_a_confirmed_violation_is_counted_as_unconfirmable() -> None:
    operation = operation_with({"n": Schema(type="integer", minimum=0.5)})
    base = exchange("op", "POST", "/api/x", "/api/x", body={"n": 1})

    result = plan(base, config=WRITES, operations={"op": operation})

    assert "unconfirmable" in reasons(result)["op"]


def test_the_rendered_query_keeps_other_parameters_and_encodes_the_value() -> None:
    result = plan(LIST)
    case = next(c for c in result.cases if c.case_class == "wrong_type")

    target, body = render_case(case)

    assert target == "/api/produtos?limite=not-a-number&ordem=asc&busca=abc"
    assert body is None


def test_the_rendered_body_is_compact_json_with_the_field_replaced_in_place() -> None:
    result = plan(CREATE, config=WRITES)
    case = next(c for c in result.cases if c.case_class == "wrong_type" and c.field == "preco")

    target, body = render_case(case)

    assert target == "/api/produtos"
    assert body == '{"nome":"Caneta","preco":"not-a-number","status":"ativo"}'
