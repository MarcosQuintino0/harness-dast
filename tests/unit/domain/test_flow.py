import pytest

from harness_dast.domain.api_model import (
    ApiSpec,
    MediaBody,
    Operation,
    Parameter,
    RequestBody,
    SuccessResponse,
)
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.errors import ConfigError, TargetError
from harness_dast.domain.flow import FlowSpec, extract_value
from tests.unit.api_helpers import obj


def flows(*bindings: dict[str, object]) -> FlowSpec:
    return FlowSpec.from_data({"schema_version": 1, "bindings": list(bindings)})


def bind(producer: str, field: str, *consumers: dict[str, str]) -> dict[str, object]:
    return {
        "produces": {"operation": producer, "field": field},
        "consumed_by": list(consumers),
    }


def to(operation: str, **target: str) -> dict[str, str]:
    return {"operation": operation, **target}


def test_from_data_accepts_the_documented_example() -> None:
    spec = flows(
        bind(
            "criarPaciente",
            "id",
            to("buscarPaciente", param="pacienteId"),
            to("criarConsulta", field="pacienteId"),
        )
    )

    assert len(spec.bindings) == 1


def test_from_data_accepts_an_empty_flows_file() -> None:
    assert FlowSpec.from_data({"schema_version": 1}).bindings == ()


def test_from_data_requires_schema_version() -> None:
    with pytest.raises(ConfigError, match="não informa schema_version"):
        FlowSpec.from_data({"bindings": []})


@pytest.mark.parametrize("data", [None, [], "x"])
def test_from_data_rejects_a_document_that_is_not_a_map(data: object) -> None:
    with pytest.raises(ConfigError, match="deve ser um mapa"):
        FlowSpec.from_data(data)


def test_from_data_rejects_a_consumer_with_both_param_and_field() -> None:
    with pytest.raises(ConfigError, match="exatamente um"):
        flows(bind("a", "id", to("b", param="x", field="y")))


def test_from_data_rejects_a_consumer_with_neither_param_nor_field() -> None:
    with pytest.raises(ConfigError, match="exatamente um"):
        flows(bind("a", "id", to("b")))


def test_from_data_rejects_a_binding_without_consumers() -> None:
    with pytest.raises(ConfigError):
        flows(bind("a", "id"))


@pytest.mark.parametrize("field", ["", "a b", "a..b", ".a", "a." + "b" * 101])
def test_from_data_rejects_malformed_field_paths(field: str) -> None:
    with pytest.raises(ConfigError):
        flows(bind("a", field, to("b", param="x")))


def test_from_data_rejects_unknown_keys() -> None:
    data = {"schema_version": 1, "bindings": [{**bind("a", "id", to("b", param="x")), "z": 1}]}

    with pytest.raises(ConfigError, match="campo desconhecido"):
        FlowSpec.from_data(data)


def test_from_data_rejects_a_target_fed_by_two_sources() -> None:
    with pytest.raises(ConfigError, match="mais de uma fonte"):
        flows(
            bind("a", "id", to("c", param="x")),
            bind("b", "id", to("c", param="x")),
        )


def test_from_data_rejects_the_same_target_twice_in_one_binding() -> None:
    with pytest.raises(ConfigError, match="mais de uma fonte"):
        flows(bind("a", "id", to("c", param="x"), to("c", param="x")))


def test_from_data_allows_the_same_name_as_param_and_as_field() -> None:
    spec = flows(bind("a", "id", to("c", param="x"), to("c", field="x")))

    assert len(spec.bindings[0].consumed_by) == 2


def test_from_data_allows_one_consumer_with_two_producers() -> None:
    spec = flows(
        bind("a1", "id", to("c", param="x")),
        bind("a2", "id", to("c", param="y")),
    )

    assert len(spec.bindings) == 2


def test_from_data_rejects_an_operation_that_consumes_from_itself() -> None:
    with pytest.raises(ConfigError, match="ciclo"):
        flows(bind("a", "id", to("a", param="x")))


def test_from_data_rejects_a_two_operation_cycle_and_names_the_path() -> None:
    with pytest.raises(ConfigError) as caught:
        flows(
            bind("a", "id", to("b", param="x")),
            bind("b", "id", to("a", param="y")),
        )

    assert "'a' -> 'b' -> 'a'" in caught.value.message


def test_from_data_rejects_a_longer_cycle() -> None:
    with pytest.raises(ConfigError, match="ciclo"):
        flows(
            bind("a", "id", to("b", param="x")),
            bind("b", "id", to("c", param="x")),
            bind("c", "id", to("a", param="x")),
        )


def test_from_data_rejects_a_chain_deeper_than_one_level() -> None:
    with pytest.raises(ConfigError) as caught:
        flows(
            bind("criarA", "id", to("criarB", field="aId")),
            bind("criarB", "id", to("buscarC", param="bId")),
        )

    assert "só um nível" in caught.value.message
    assert "'criarB'" in caught.value.message


def test_from_data_accepts_a_diamond_shape_that_is_not_a_chain() -> None:
    spec = flows(
        bind("a", "id", to("c", param="x"), to("d", param="x")),
        bind("b", "id", to("c", param="y"), to("d", param="y")),
    )

    assert spec.execution_order(["c", "d", "a", "b"]) == ("a", "b", "c", "d")


def test_find_cycle_skips_already_explored_nodes_when_graph_has_shared_targets() -> None:
    spec = flows(
        bind("a", "id", to("x", param="p")),
        bind("b", "id", to("x", param="q")),
        bind("c", "id", to("x", param="r")),
    )

    assert spec.execution_order(["x", "a", "b", "c"]) == ("a", "b", "c", "x")


def test_execution_order_puts_producers_before_consumers() -> None:
    spec = flows(bind("criar", "id", to("buscar", param="id"), to("apagar", param="id")))

    order = spec.execution_order(["buscar", "apagar", "listar", "criar"])

    assert order == ("listar", "criar", "buscar", "apagar")


def test_execution_order_keeps_the_given_order_when_there_are_no_dependencies() -> None:
    assert FlowSpec(schema_version=1).execution_order(["b", "a", "c"]) == ("b", "a", "c")


def test_execution_order_ignores_operations_that_are_not_in_the_list() -> None:
    spec = flows(bind("x", "id", to("y", param="p")))

    assert spec.execution_order(["a", "b"]) == ("a", "b")


def test_execution_order_is_deterministic() -> None:
    spec = flows(bind("p", "id", to("c1", param="x"), to("c2", param="x")))
    ids = ["c2", "c1", "z", "p"]

    assert spec.execution_order(ids) == spec.execution_order(list(ids))


def test_extract_value_reads_nested_keys_and_list_indexes() -> None:
    body: JsonValue = {"data": {"items": [{"id": 5}, {"id": 6}]}}

    assert extract_value(body, "data.items.1.id") == 6


def test_extract_value_returns_text_values() -> None:
    assert extract_value({"id": "abc"}, "id") == "abc"


@pytest.mark.parametrize(
    "body",
    [{}, [], "texto", None, {"a": [1]}],
)
def test_extract_value_raises_target_error_when_field_is_absent(body: object) -> None:
    with pytest.raises(TargetError, match="não contém o campo 'id'"):
        extract_value(body, "id")  # type: ignore[arg-type]  # corpo malformado de propósito


@pytest.mark.parametrize("value", [None, True, 1.5, [1], {"a": 1}])
def test_extract_value_rejects_values_that_cannot_be_chained(value: object) -> None:
    with pytest.raises(TargetError, match="não é texto nem inteiro"):
        extract_value({"id": value}, "id")  # type: ignore[dict-item]  # valores variados


def test_extract_value_rejects_an_index_past_the_end() -> None:
    with pytest.raises(TargetError):
        extract_value({"items": [{"id": 1}]}, "items.3.id")


def test_extract_value_never_echoes_the_response_content() -> None:
    with pytest.raises(TargetError) as caught:
        extract_value({"id": {"segredo": "TOKEN-SECRETO"}}, "id")

    assert "TOKEN-SECRETO" not in caught.value.message


def test_resolve_bindings_extracts_params_and_fields_for_the_consumer() -> None:
    spec = flows(
        bind("criar", "data.id", to("buscar", param="pid"), to("agendar", field="paciente.id"))
    )
    responses: dict[str, JsonValue] = {"criar": {"data": {"id": 42}}}

    assert spec.resolve_bindings("buscar", responses).params == {"pid": 42}
    assert spec.resolve_bindings("agendar", responses).fields == {"paciente.id": 42}


def test_resolve_bindings_is_empty_for_an_operation_that_consumes_nothing() -> None:
    resolved = flows(bind("a", "id", to("b", param="x"))).resolve_bindings("zzz", {})

    assert resolved.params == {}
    assert resolved.fields == {}


def test_resolve_bindings_raises_when_the_producer_response_is_missing() -> None:
    spec = flows(bind("a", "id", to("b", param="x")))

    with pytest.raises(TargetError, match="Falta a resposta"):
        spec.resolve_bindings("b", {})


def test_resolve_bindings_raises_when_the_field_is_missing_from_the_response() -> None:
    spec = flows(bind("a", "id", to("b", param="x")))

    with pytest.raises(TargetError, match="não contém"):
        spec.resolve_bindings("b", {"a": {"outro": 1}})


def api() -> ApiSpec:
    created = Schema(type="object", properties={"id": Schema(type="integer")})
    return ApiSpec(
        title="t",
        version="1",
        operations=(
            Operation(
                operation_id="criar",
                method="post",
                path="/p",
                success_responses=(SuccessResponse(status="201", body_schema=created),),
            ),
            Operation(
                operation_id="semEsquema",
                method="post",
                path="/q",
                success_responses=(SuccessResponse(status="201"),),
            ),
            Operation(
                operation_id="buscar",
                method="get",
                path="/p/{pid}",
                parameters=(Parameter(name="pid", location="path", required=True),),
            ),
            Operation(
                operation_id="agendar",
                method="post",
                path="/a",
                request_body=RequestBody(
                    media=(
                        MediaBody(
                            media_type="application/json",
                            body_schema=obj(paciente=obj(id=Schema(type="integer"))),
                        ),
                    )
                ),
            ),
            Operation(operation_id="semCorpo", method="post", path="/s"),
        ),
    )


def test_validate_against_accepts_a_consistent_flow() -> None:
    spec = flows(bind("criar", "id", to("buscar", param="pid"), to("agendar", field="paciente.id")))

    spec.validate_against(api())


def test_validate_against_accepts_a_producer_without_declared_response_schema() -> None:
    flows(bind("semEsquema", "qualquer.coisa", to("buscar", param="pid"))).validate_against(api())


@pytest.mark.parametrize(
    ("binding", "text"),
    [
        (bind("nada", "id", to("buscar", param="pid")), "'nada'"),
        (bind("criar", "id", to("nada", param="pid")), "'nada'"),
        (bind("criar", "naoExiste", to("buscar", param="pid")), "não tem o campo 'naoExiste'"),
        (bind("criar", "id", to("buscar", param="outro")), "não tem o parâmetro 'outro'"),
        (
            bind("criar", "id", to("agendar", field="paciente.cpf")),
            "não tem o campo 'paciente.cpf'",
        ),
        (bind("criar", "id", to("semCorpo", field="x")), "não tem o campo 'x' no corpo"),
    ],
)
def test_validate_against_rejects_unknown_operations_params_and_fields(
    binding: dict[str, object], text: str
) -> None:
    with pytest.raises(ConfigError) as caught:
        flows(binding).validate_against(api())

    assert text in caught.value.message
