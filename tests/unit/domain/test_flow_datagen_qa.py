# ruff: noqa: PT018, RUF007, SIM105, S105
"""QA independente de `data-rules.yml` (`DataRules`) e `flows.yml` (`FlowSpec`).

Contrato (docstrings): regras validadas contra um catálogo FECHADO de geradores; duas regras com
o mesmo `match` são ambíguas e o arquivo é recusado; a precedência é determinística; o
encadeamento é um grafo sem ciclos, com cada alvo tendo uma só fonte e cadeia até
`MAX_FLOW_DEPTH`; entrada inválida vira `ConfigError` sem repetir os valores recebidos.
"""

import math

import pytest

from harness_dast.domain.datagen import MAX_RULES, DataRules
from harness_dast.domain.errors import ConfigError, TargetError
from harness_dast.domain.flow import (
    MAX_BINDINGS,
    MAX_CONSUMERS,
    MAX_FLOW_DEPTH,
    FlowSpec,
    extract_value,
)


def rules(*items: object) -> dict[str, object]:
    return {"schema_version": 1, "rules": list(items)}


def rule(field: str = "cpf", generator: str = "br.cpf", **extra: object) -> dict[str, object]:
    return {"match": {"field": field}, "generator": generator, **extra}


def single(**fields: object) -> dict[str, object]:
    """Uma regra com `match.field = x`, ao qual `fields` se sobrepõe."""
    return rules({"match": {"field": "x"}, "generator": "br.cpf", **fields})


# ------------------------------------------------------------------------- data-rules


def test_data_rules_accepts_a_minimal_valid_document() -> None:
    parsed = DataRules.from_data(rules(rule()))

    assert len(parsed.rules) == 1


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        "x",
        42,
        {},
        {"rules": []},
        {"schema_version": 0, "rules": []},
        {"schema_version": 2, "rules": []},
        {"schema_version": "1", "rules": []},
        {"schema_version": True, "rules": []},
        {"schema_version": 1.0, "rules": []},
        {"schema_version": 1, "rules": {}},
        {"schema_version": 1, "rules": "x"},
        {"schema_version": 1, "rules": [], "extra": 1},
        rules("texto"),
        rules({}),
        rules({"match": {}, "generator": "br.cpf"}),
        rules({"match": {"field": ""}, "generator": "br.cpf"}),
        rules({"match": {"field": "a..b"}, "generator": "br.cpf"}),
        rules({"match": {"field": ".a"}, "generator": "br.cpf"}),
        rules({"match": {"field": "a b"}, "generator": "br.cpf"}),
        rules({"match": {"field": "a\x00b"}, "generator": "br.cpf"}),
        rules({"match": {"field": "a" * 101}, "generator": "br.cpf"}),
        rules({"match": {"field": ".".join(["a"] * 11)}, "generator": "br.cpf"}),
        rules({"match": {"field": "cpf", "location": "everywhere"}, "generator": "br.cpf"}),
        rules({"match": {"field": "cpf", "operation": ""}, "generator": "br.cpf"}),
        rules({"match": {"field": "cpf"}, "generator": "inexistente"}),
        rules({"match": {"field": "cpf"}, "generator": "eval"}),
        rules({"match": {"field": "cpf"}, "generator": ""}),
        rules({"match": {"field": "cpf"}, "generator": "__import__('os')"}),
        rules({"match": {"field": "cpf"}, "generator": "br.cpf", "extra": True}),
        rules({"match": {"field": "cpf", "regex": ".*"}, "generator": "br.cpf"}),
        rules({"match": {"field": "cpf"}, "generator": "br.cpf", "args": {"inexistente": 1}}),
        rules({"match": {"field": "cpf"}, "generator": "br.cpf", "args": {"formatted": "sim"}}),
        rules({"match": {"field": "cpf"}, "generator": "br.cpf", "args": {"formatted": 1}}),
        rules({"match": {"field": "cpf"}, "generator": "br.cpf", "args": []}),
        rules({"match": {"field": "n"}, "generator": "numeric"}),
        rules({"match": {"field": "n"}, "generator": "numeric", "args": {"digits": 0}}),
        rules({"match": {"field": "n"}, "generator": "numeric", "args": {"digits": 31}}),
        rules({"match": {"field": "n"}, "generator": "numeric", "args": {"digits": True}}),
        rules({"match": {"field": "n"}, "generator": "numeric", "args": {"digits": 2.0}}),
        rules({"match": {"field": "n"}, "generator": "numeric", "args": {"digits": "3"}}),
        rules({"match": {"field": "n"}, "generator": "integer", "args": {"min": 5, "max": 1}}),
        rules({"match": {"field": "d"}, "generator": "date", "args": {"min_offset_days": 40000}}),
        rules({"match": {"field": "c"}, "generator": "choice", "args": {"values": []}}),
        rules({"match": {"field": "c"}, "generator": "choice", "args": {"values": [[1]]}}),
        rules({"match": {"field": "c"}, "generator": "choice", "args": {"values": [{"a": 1}]}}),
        rules({"match": {"field": "c"}, "generator": "constant", "args": {"value": {"a": 1}}}),
        rules({"match": {"field": "c"}, "generator": "constant", "args": {"value": "x" * 100_000}}),
        rules({"match": {"field": "b"}, "generator": "boolean", "unique": True}),
        rules(
            {
                "match": {"field": "b"},
                "generator": "choice",
                "args": {"values": [1]},
                "unique": True,
            }
        ),
        single(unique="yes"),
    ],
)
def test_data_rules_refuses_invalid_documents_with_config_error(document: object) -> None:
    with pytest.raises(ConfigError):
        DataRules.from_data(document)


def test_data_rules_refuses_two_rules_with_the_same_match() -> None:
    with pytest.raises(ConfigError):
        DataRules.from_data(rules(rule("cpf"), rule("cpf", "br.cnpj")))


def test_data_rules_accepts_the_same_field_when_operation_or_location_differ() -> None:
    document = rules(
        rule("cpf"),
        {"match": {"field": "cpf", "operation": "criar"}, "generator": "br.cnpj"},
        {"match": {"field": "cpf", "location": "query"}, "generator": "br.cnpj"},
    )

    assert len(DataRules.from_data(document).rules) == 3


def test_data_rules_refuses_more_rules_than_the_limit() -> None:
    many = [rule(f"campo{n}") for n in range(MAX_RULES + 1)]

    with pytest.raises(ConfigError):
        DataRules.from_data(rules(*many))


def test_data_rules_error_never_echoes_secret_looking_values() -> None:
    secret = "SEGREDO-NO-VALOR-9876"
    document = rules(
        {"match": {"field": "x"}, "generator": "constant", "args": {"value": {"k": secret}}}
    )

    with pytest.raises(ConfigError) as caught:
        DataRules.from_data(document)

    assert secret not in caught.value.message
    assert secret not in (caught.value.hint or "")


def test_data_rules_resolve_prefers_operation_then_depth_then_location() -> None:
    parsed = DataRules.from_data(
        rules(
            rule("cpf", "br.cpf"),
            {"match": {"field": "pessoa.cpf"}, "generator": "br.cnpj"},
            {"match": {"field": "cpf", "location": "body"}, "generator": "br.cep"},
            {"match": {"field": "cpf", "operation": "criar"}, "generator": "uuid"},
        )
    )

    by_operation = parsed.resolve("criar", "body", ("pessoa", "cpf"))
    by_depth = parsed.resolve("outra", "body", ("pessoa", "cpf"))
    by_location = parsed.resolve("outra", "body", ("cpf",))
    by_default = parsed.resolve("outra", "query", ("cpf",))
    nothing = parsed.resolve("outra", "body", ("rg",))

    assert by_operation is not None and by_operation.rule.generator == "uuid"
    assert by_depth is not None and by_depth.rule.generator == "br.cnpj"
    assert by_location is not None and by_location.rule.generator == "br.cep"
    assert by_default is not None and by_default.rule.generator == "br.cpf"
    assert nothing is None


def test_data_rules_resolve_is_independent_of_the_order_of_the_rules() -> None:
    first = rule("cpf", "br.cpf")
    second = {"match": {"field": "cpf", "location": "body"}, "generator": "br.cep"}

    a = DataRules.from_data(rules(first, second)).resolve("x", "body", ("cpf",))
    b = DataRules.from_data(rules(second, first)).resolve("x", "body", ("cpf",))

    assert a is not None and b is not None
    assert a.rule.generator == b.rule.generator == "br.cep"


def test_data_rules_field_matches_only_the_end_of_the_path() -> None:
    parsed = DataRules.from_data(rules(rule("cpf")))

    assert parsed.resolve("x", "body", ("cpf",)) is not None
    assert parsed.resolve("x", "body", ("a", "cpf")) is not None
    assert parsed.resolve("x", "body", ("cpf", "a")) is None
    assert parsed.resolve("x", "body", ("meucpf",)) is None


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_data_rules_refuses_non_finite_numbers_in_arguments(bad: float) -> None:
    # `nan`/`inf` não existem em JSON: um valor assim viraria `NaN` no corpo enviado ao alvo.
    document = rules({"match": {"field": "n"}, "generator": "constant", "args": {"value": bad}})

    with pytest.raises(ConfigError):
        DataRules.from_data(document)


# --------------------------------------------------------------------------------- flows


def binding(producer: str, field: str, *consumers: tuple[str, str, str]) -> dict[str, object]:
    return {
        "produces": {"operation": producer, "field": field},
        "consumed_by": [{"operation": op, kind: name} for op, kind, name in consumers],
    }


def flows(*items: object) -> dict[str, object]:
    return {"schema_version": 1, "bindings": list(items)}


def test_flow_spec_accepts_a_simple_chain() -> None:
    spec = FlowSpec.from_data(flows(binding("criar", "id", ("buscar", "param", "pacienteId"))))

    assert spec.execution_order(["buscar", "criar"]) == ("criar", "buscar")


def _produces(**changes: object) -> dict[str, object]:
    return {
        "produces": {"operation": "a", "field": "id", **changes},
        "consumed_by": [{"operation": "b", "param": "x"}],
    }


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {},
        {"schema_version": 2, "bindings": []},
        {"schema_version": 1, "bindings": {}},
        {"schema_version": 1, "bindings": [], "extra": 1},
        flows({}),
        flows({"produces": {"operation": "a", "field": "id"}}),
        flows({"produces": {"operation": "a", "field": "id"}, "consumed_by": []}),
        flows(_produces(operation="")),
        flows(_produces(field="a..b")),
        flows(_produces(field="")),
        flows({"produces": {"operation": "a", "field": "id"}, "consumed_by": [{"operation": "b"}]}),
        flows(
            {
                "produces": {"operation": "a", "field": "id"},
                "consumed_by": [{"operation": "b", "param": "x", "field": "y"}],
            }
        ),
        flows(
            {
                "produces": {"operation": "a", "field": "id"},
                "consumed_by": [{"operation": "b", "param": "x", "extra": 1}],
            }
        ),
        flows(binding("a", "id", ("a", "param", "x"))),
        flows(binding("a", "id", ("b", "param", "x")), binding("b", "id", ("a", "param", "y"))),
        flows(
            binding("a", "id", ("b", "param", "x")),
            binding("b", "id", ("c", "param", "x")),
            binding("c", "id", ("a", "param", "x")),
        ),
        flows(binding("a", "id", ("c", "param", "x")), binding("b", "id", ("c", "param", "x"))),
    ],
)
def test_flow_spec_refuses_invalid_documents_with_config_error(document: object) -> None:
    with pytest.raises(ConfigError):
        FlowSpec.from_data(document)


def test_flow_spec_refuses_a_chain_deeper_than_the_limit() -> None:
    names = [f"op{n}" for n in range(MAX_FLOW_DEPTH + 1)]
    bindings = [binding(a, "id", (b, "param", "x")) for a, b in zip(names, names[1:], strict=False)]

    with pytest.raises(ConfigError):
        FlowSpec.from_data(flows(*bindings))


def test_flow_spec_accepts_a_chain_exactly_at_the_limit() -> None:
    names = [f"op{n}" for n in range(MAX_FLOW_DEPTH)]
    bindings = [binding(a, "id", (b, "param", "x")) for a, b in zip(names, names[1:], strict=False)]

    assert len(FlowSpec.from_data(flows(*bindings)).bindings) == MAX_FLOW_DEPTH - 1


def test_flow_spec_refuses_too_many_bindings_and_too_many_consumers() -> None:
    too_many = [binding(f"p{n}", "id", (f"c{n}", "param", "x")) for n in range(MAX_BINDINGS + 1)]
    crowded = binding("a", "id", *[(f"c{n}", "param", "x") for n in range(MAX_CONSUMERS + 1)])

    with pytest.raises(ConfigError):
        FlowSpec.from_data(flows(*too_many))
    with pytest.raises(ConfigError):
        FlowSpec.from_data(flows(crowded))


def test_flow_spec_validation_terminates_on_a_wide_dag_at_the_binding_limit() -> None:
    # 200 bindings com 50 consumidores cada, em DAG largo: a validação precisa terminar (sem
    # recursão profunda nem explosão) e devolver ConfigError ou um modelo.
    bindings = [
        binding(f"op{n}", "id", *[(f"op{n + 1}", "param", f"p{k}") for k in range(50)])
        for n in range(MAX_BINDINGS)
    ]

    try:
        FlowSpec.from_data(flows(*bindings))
    except ConfigError:
        pass


def test_flow_execution_order_places_every_producer_before_its_consumers() -> None:
    spec = FlowSpec.from_data(
        flows(binding("a", "id", ("b", "param", "x")), binding("b", "id", ("c", "param", "x")))
    )

    order = spec.execution_order(["c", "b", "a", "z"])

    assert order.index("a") < order.index("b") < order.index("c")
    assert set(order) == {"a", "b", "c", "z"}


def test_flow_execution_order_is_deterministic_and_ignores_unknown_operations() -> None:
    spec = FlowSpec.from_data(flows(binding("a", "id", ("ghost", "param", "x"))))

    assert spec.execution_order(["z", "a"]) == ("z", "a")
    assert spec.execution_order(["z", "a"]) == spec.execution_order(["z", "a"])


def test_flow_resolve_bindings_reads_values_from_the_producer_response() -> None:
    spec = FlowSpec.from_data(
        flows(
            {
                "produces": {"operation": "criar", "field": "data.id"},
                "consumed_by": [
                    {"operation": "buscar", "param": "pid"},
                    {"operation": "buscar", "field": "ref"},
                ],
            }
        )
    )

    resolved = spec.resolve_bindings("buscar", {"criar": {"data": {"id": 77}}})

    assert resolved.params == {"pid": 77}
    assert resolved.fields == {"ref": 77}


def test_flow_resolve_bindings_fails_with_target_error_when_producer_did_not_run() -> None:
    spec = FlowSpec.from_data(flows(binding("criar", "id", ("buscar", "param", "pid"))))

    with pytest.raises(TargetError):
        spec.resolve_bindings("buscar", {})


@pytest.mark.parametrize(
    ("body", "path"),
    [
        ({"id": None}, "id"),
        ({"id": True}, "id"),
        ({"id": 1.5}, "id"),
        ({"id": [1]}, "id"),
        ({"id": {"a": 1}}, "id"),
        ({}, "id"),
        ({"a": [1]}, "a.5"),
        ({"a": [1]}, "a.x"),
        ([], "0"),
        ("texto", "id"),
        (None, "id"),
        ({"a": {"b": 1}}, "a.b.c"),
    ],
)
def test_extract_value_refuses_missing_paths_and_non_simple_values(body: object, path: str) -> None:
    with pytest.raises(TargetError):
        extract_value(body, path)  # type: ignore[arg-type]


def test_extract_value_never_echoes_the_response_content_in_the_error() -> None:
    with pytest.raises(TargetError) as caught:
        extract_value({"id": {"senha": "SEGREDO-RESPOSTA-123"}}, "id")

    assert "SEGREDO-RESPOSTA-123" not in caught.value.message


@pytest.mark.parametrize(
    ("body", "path", "expected"),
    [({"id": 5}, "id", 5), ({"id": "abc"}, "id", "abc"), ({"a": [{"b": 9}]}, "a.0.b", 9)],
)
def test_extract_value_reads_text_and_integers_by_path(
    body: object, path: str, expected: object
) -> None:
    assert extract_value(body, path) == expected  # type: ignore[arg-type]
