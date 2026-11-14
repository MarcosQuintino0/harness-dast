"""Equivalência de respostas, campos fora do esquema e efeito de um campo injetado."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.authz_compare import (
    MAX_PARSE_DEPTH,
    MAX_PATHS,
    bodies_equivalent,
    has_empty_list,
    holds_value,
    injected_effect,
    is_success_status,
    judge_replay,
    parse_json,
    strip_volatile,
    unexpected_fields,
)
from harness_dast.domain.authz_config import DEFAULT_VOLATILE_FIELDS

VOLATILE = frozenset(DEFAULT_VOLATILE_FIELDS)
STR = Schema(type="string")
INT = Schema(type="integer")


def val(value: object) -> JsonValue:
    """Valor Python simples como `JsonValue` (o mypy não infere o tipo recursivo)."""
    result: JsonValue = json.loads(json.dumps(value))
    return result


def j(value: object) -> bytes:
    return json.dumps(value).encode()


def obj(**properties: Schema) -> Schema:
    return Schema(type="object", properties=properties)


# --- equivalência -----------------------------------------------------------------------


def test_equal_bodies_are_equivalent_regardless_of_key_order() -> None:
    assert bodies_equivalent(j({"a": 1, "b": 2}), j({"b": 2, "a": 1}), VOLATILE)


def test_volatile_fields_at_any_depth_are_ignored() -> None:
    first = j({"id": 1, "requestId": "a", "meta": {"timestamp": 1, "x": 2}})
    second = j({"id": 1, "request_id": "b", "meta": {"Timestamp": 99, "x": 2}})

    assert bodies_equivalent(first, second, VOLATILE)


def test_a_different_value_is_not_equivalent() -> None:
    assert not bodies_equivalent(j({"id": 1, "nome": "A"}), j({"id": 1, "nome": "B"}), VOLATILE)


def test_a_declared_volatile_field_is_ignored_only_when_declared() -> None:
    first, second = j({"id": 1, "versao": 1}), j({"id": 1, "versao": 2})

    assert not bodies_equivalent(first, second, VOLATILE)
    assert bodies_equivalent(first, second, VOLATILE | {"versao"})


def test_non_json_bodies_are_compared_byte_for_byte() -> None:
    assert bodies_equivalent(b"texto", b"texto", VOLATILE)
    assert not bodies_equivalent(b"texto", b"outro", VOLATILE)


def test_json_and_non_json_are_not_equivalent() -> None:
    assert not bodies_equivalent(j({"a": 1}), b"nao json", VOLATILE)


def test_two_empty_bodies_are_equivalent() -> None:
    assert bodies_equivalent(b"", b"  ", VOLATILE)


def test_malformed_and_deeply_nested_json_does_not_crash() -> None:
    deep = b"[" * 5000 + b"]" * 5000

    assert parse_json(b"{oops") is None
    assert parse_json(b"\xff\xfe") is None
    assert parse_json(deep) is None
    assert bodies_equivalent(deep, deep, VOLATILE)


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(st.text(min_size=1, max_size=6), children, max_size=3)
    ),
    max_leaves=12,
)


@given(json_values)
def test_equivalence_is_reflexive(value: JsonValue) -> None:
    assert bodies_equivalent(j(value), j(value), VOLATILE)


@given(json_values, json_values)
def test_equivalence_is_symmetric(first: JsonValue, second: JsonValue) -> None:
    assert bodies_equivalent(j(first), j(second), VOLATILE) == bodies_equivalent(
        j(second), j(first), VOLATILE
    )


@given(json_values)
def test_stripping_volatile_fields_is_idempotent(value: JsonValue) -> None:
    once = strip_volatile(value, VOLATILE)

    assert strip_volatile(once, VOLATILE) == once


# --- veredito ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("baseline", "replay", "equivalent", "expected"),
    [
        (200, 200, True, "allowed_equivalent"),
        (200, 200, False, "allowed_different"),
        (200, 204, True, "allowed_equivalent"),
        (200, 403, False, "denied"),
        (200, 404, False, "denied"),
        (200, 401, False, "denied"),
        (200, 400, False, "denied"),
        (200, 500, False, "error"),
        (200, 503, False, "error"),
        (200, None, False, "error"),
        (403, 200, True, "baseline_failed"),
        (None, 200, True, "baseline_failed"),
        (404, 404, True, "baseline_failed"),
    ],
)
def test_the_verdict_table(
    baseline: int | None, replay: int | None, equivalent: bool, expected: str
) -> None:
    assert judge_replay(baseline, replay, equivalent=equivalent) == expected


def test_only_2xx_is_success() -> None:
    assert [is_success_status(s) for s in (199, 200, 299, 300, None)] == [
        False,
        True,
        True,
        False,
        False,
    ]


# --- campos fora do esquema ---------------------------------------------------------------


def test_extra_fields_in_a_list_of_items_are_reported_with_their_path() -> None:
    schema = obj(items=Schema(type="array", items=obj(id=INT, nome=STR)))
    body = val({"items": [{"id": 1, "nome": "a", "passwordHash": "x"}, {"id": 2, "nome": "b"}]})

    assert unexpected_fields(schema, body) == ("items[].passwordHash",)


def test_an_empty_list_where_the_schema_declares_items_has_nothing_to_compare() -> None:
    schema = obj(items=Schema(type="array", items=obj(id=INT)))

    assert has_empty_list(schema, val({"items": []})) is True
    assert has_empty_list(schema, val({"items": [{"id": 1}]})) is False
    assert has_empty_list(obj(id=INT), val({"id": 1})) is False


def test_a_matching_response_has_no_unexpected_field() -> None:
    assert unexpected_fields(obj(id=INT, nome=STR), val({"id": 1, "nome": "a"})) == ()


def test_nested_objects_are_walked() -> None:
    schema = obj(dono=obj(nome=STR))

    assert unexpected_fields(schema, val({"dono": {"nome": "a", "cpf": "1"}})) == ("dono.cpf",)


def test_fields_declared_through_all_of_and_one_of_are_known() -> None:
    schema = Schema(all_of=(obj(id=INT), obj(nome=STR)), one_of=(obj(extra=STR),))

    assert unexpected_fields(schema, val({"id": 1, "nome": "a", "extra": "x"})) == ()


def test_a_free_form_object_never_reports_fields() -> None:
    assert unexpected_fields(Schema(type="object"), val({"qualquer": 1})) == ()
    assert unexpected_fields(Schema(), val({"qualquer": 1})) == ()


def test_a_truncated_schema_node_is_opaque() -> None:
    schema = obj(dono=Schema(truncated=True))

    assert unexpected_fields(schema, val({"dono": {"x": 1}})) == ()


def test_scalar_and_null_bodies_report_nothing() -> None:
    assert unexpected_fields(obj(id=INT), 5) == ()
    assert unexpected_fields(obj(id=INT), None) == ()


def test_reported_paths_are_unique_and_capped() -> None:
    body = val({f"campo{i}": i for i in range(100)})

    found = unexpected_fields(obj(id=INT), body)

    assert len(found) == MAX_PATHS
    assert len(set(found)) == len(found)


def test_the_reported_paths_never_contain_values() -> None:
    found = unexpected_fields(obj(id=INT), val({"segredo": "VALOR-SECRETO-123"}))

    assert "VALOR-SECRETO-123" not in "".join(found)


# --- efeito de um campo injetado ------------------------------------------------------------


def test_effect_is_found_when_a_differently_named_field_takes_the_value() -> None:
    before = val({"id": 1, "papel": "paciente"})
    after = val({"id": 1, "papel": "admin"})

    changed, previous = injected_effect(before, after, "role", "admin")

    assert changed == ("papel",)
    assert previous == "paciente"


def test_no_effect_when_the_value_was_already_there() -> None:
    state = val({"papel": "admin"})

    assert injected_effect(state, state, "role", "admin") == ((), None)


def test_no_effect_when_nothing_changed() -> None:
    state = val({"papel": "paciente"})

    assert injected_effect(state, state, "role", "admin")[0] == ()


def test_effect_without_a_previous_read_needs_the_same_field_name() -> None:
    assert injected_effect(None, val({"role": "admin"}), "role", "admin")[0] == ("role",)
    assert injected_effect(None, val({"papel": "admin"}), "role", "admin")[0] == ()


def test_the_type_matters_in_the_effect() -> None:
    assert injected_effect(val({"admin": 0}), val({"admin": 1}), "admin", True)[0] == ()
    assert injected_effect(val({"admin": False}), val({"admin": True}), "admin", True)[0] == (
        "admin",
    )


def test_no_effect_without_a_response() -> None:
    assert injected_effect(val({"a": 1}), None, "role", "admin") == ((), None)


def test_a_new_path_that_appears_with_the_value_is_an_effect() -> None:
    changed, previous = injected_effect(
        val({"id": 1}), val({"id": 1, "role": "admin"}), "role", "admin"
    )

    assert changed == ("role",)
    assert previous is None


def test_holds_value_checks_exact_value_and_type() -> None:
    body = val({"papel": "admin", "n": 1})

    assert holds_value(body, ("papel",), "admin")
    assert not holds_value(body, ("papel",), "paciente")
    assert not holds_value(body, ("n",), True)
    assert not holds_value(None, ("papel",), "admin")
    assert not holds_value(body, ("ausente",), "admin")


def test_nesting_just_over_the_limit_is_refused_whatever_the_interpreter_allows() -> None:
    over = b"[" * (MAX_PARSE_DEPTH + 1) + b"]" * (MAX_PARSE_DEPTH + 1)
    inside = b"[" * MAX_PARSE_DEPTH + b"]" * MAX_PARSE_DEPTH

    assert parse_json(over) is None
    assert parse_json(inside) is not None


def test_brackets_inside_strings_do_not_count_as_nesting() -> None:
    body = ('{"a": "' + "[" * 500 + '\\"[' + '"}').encode()

    assert parse_json(body) == {"a": "[" * 500 + '"['}
