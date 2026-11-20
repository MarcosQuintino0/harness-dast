"""Valores que o esquema proíbe: cada classe, conferida por `check_schema` (ADR 0051)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.negative_values import (
    CLASS_ORDER,
    MAX_VALUE_CHARS,
    CaseClass,
    Proposal,
    expected_code,
    propose,
    propose_missing,
)
from harness_dast.domain.schema_check import check_schema

FORBIDDEN_CHARS = ("'", '"', "<", ">", "%", "/", "\\", "..", ";", "&", "?", "#")


def proposal(schema: Schema, case_class: CaseClass, *, in_query: bool = False) -> Proposal:
    found = propose(schema, case_class, in_query=in_query)
    assert isinstance(found, Proposal), found
    return found


def test_below_minimum_is_one_under_the_limit_and_confirmed_by_the_schema() -> None:
    schema = Schema(type="integer", minimum=1)

    found = proposal(schema, "below_minimum")

    assert found.value == 0
    assert found.declared == "minimum 1"
    assert check_schema(schema, found.value) == ("range",)


def test_an_exclusive_minimum_uses_the_limit_itself() -> None:
    schema = Schema(type="number", minimum=0, exclusive_minimum=True)

    found = proposal(schema, "below_minimum")

    assert found.value == 0
    assert found.declared == "exclusive minimum 0"
    assert check_schema(schema, found.value) == ("range",)


def test_above_maximum_is_one_over_and_an_exclusive_maximum_uses_the_limit() -> None:
    assert proposal(Schema(type="integer", maximum=100), "above_maximum").value == 101
    exclusive = Schema(type="integer", maximum=10, exclusive_maximum=True)
    assert proposal(exclusive, "above_maximum").value == 10


def test_a_fractional_limit_on_an_integer_cannot_be_confirmed_and_is_dropped() -> None:
    assert propose(Schema(type="integer", minimum=0.5), "below_minimum", in_query=False) == (
        "unconfirmable"
    )


def test_a_missing_limit_makes_the_class_not_applicable() -> None:
    assert propose(Schema(type="integer"), "below_minimum", in_query=False) == "not_applicable"
    assert propose(Schema(type="integer"), "above_maximum", in_query=False) == "not_applicable"


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        (Schema(type="integer"), "not-a-number"),
        (Schema(type="number"), "not-a-number"),
        (Schema(type="boolean"), "not-a-boolean"),
        (Schema(type="string"), 12345),
    ],
)
def test_wrong_type_sends_a_value_of_another_type(schema: Schema, value: JsonValue) -> None:
    found = proposal(schema, "wrong_type")

    assert found.value == value
    assert check_schema(schema, found.value) == ("type",)


def test_wrong_type_in_a_text_query_parameter_does_not_apply_because_everything_is_text() -> None:
    assert propose(Schema(type="string"), "wrong_type", in_query=True) == "not_applicable"
    assert proposal(Schema(type="integer"), "wrong_type", in_query=True).value == "not-a-number"


def test_wrong_type_does_not_apply_to_a_field_with_enum() -> None:
    schema = Schema(type="string", enum=("a", "b"))

    assert propose(schema, "wrong_type", in_query=False) == "not_applicable"


@pytest.mark.parametrize("schema", [Schema(type="object"), Schema(type="array"), Schema()])
def test_no_class_applies_to_objects_lists_or_untyped_schemas(schema: Schema) -> None:
    assert {propose(schema, name, in_query=False) for name in CLASS_ORDER} == {"not_applicable"}


def test_not_in_enum_for_text_and_for_numbers() -> None:
    text = Schema(type="string", enum=("ativo", "inativo"))
    numbers = Schema(type="integer", enum=(1, 2, 7))

    assert proposal(text, "not_in_enum").value == "not-in-enum"
    assert proposal(numbers, "not_in_enum").value == 8
    assert check_schema(numbers, 8) == ("enum",)
    assert proposal(numbers, "not_in_enum").declared == "enum de 3 valor(es)"


def test_an_empty_or_mixed_enum_cannot_produce_a_value() -> None:
    assert propose(Schema(type="string", enum=()), "not_in_enum", in_query=False) == (
        "not_applicable"
    )
    mixed = Schema(type="string", enum=("a", 1))
    assert propose(mixed, "not_in_enum", in_query=False) == "not_applicable"


def test_too_long_is_one_over_max_length_and_zero_max_length_gives_one_character() -> None:
    assert proposal(Schema(type="string", max_length=3), "too_long").value == "aaaa"
    assert proposal(Schema(type="string", max_length=0), "too_long").value == "a"


def test_max_length_above_the_cap_is_not_applicable_to_keep_the_value_short() -> None:
    schema = Schema(type="string", max_length=MAX_VALUE_CHARS)

    assert propose(schema, "too_long", in_query=False) == "not_applicable"


def test_too_short_is_empty_for_min_length_one_and_none_for_zero_or_missing() -> None:
    assert proposal(Schema(type="string", min_length=1), "too_short").value == ""
    assert proposal(Schema(type="string", min_length=4), "too_short").value == "aaa"
    assert propose(Schema(type="string", min_length=0), "too_short", in_query=False) == (
        "not_applicable"
    )
    assert propose(Schema(type="string"), "too_short", in_query=False) == "not_applicable"


def test_a_value_the_schema_does_not_flag_with_exactly_the_class_code_is_discarded() -> None:
    # `enum` junto de `minimum`: o valor abaixo do mínimo também sai do `enum` (dois códigos).
    schema = Schema(type="integer", minimum=5, enum=(5, 6))

    assert propose(schema, "below_minimum", in_query=False) == "unconfirmable"


@pytest.mark.parametrize(
    "schema",
    [
        Schema(type="integer", minimum=1, truncated=True),
        Schema(type="integer", minimum=1, read_only=True),
    ],
)
def test_a_truncated_or_read_only_schema_is_never_touched(schema: Schema) -> None:
    assert propose(schema, "below_minimum", in_query=False) == "not_applicable"


def test_a_null_type_is_not_applicable() -> None:
    assert propose(Schema(type="null"), "wrong_type", in_query=False) == "not_applicable"


def test_missing_required_removes_a_required_field_that_is_in_the_body() -> None:
    container = Schema(
        type="object", required=("nome",), properties={"nome": Schema(type="string")}
    )

    found = propose_missing(container, {"nome": "x", "preco": 1}, "nome")

    assert isinstance(found, Proposal)
    assert found.remove is True
    assert found.declared == "required"
    assert found.case_class == "missing_required"


def test_missing_required_does_not_apply_to_an_optional_or_absent_field() -> None:
    container = Schema(type="object", required=("nome",))

    assert propose_missing(container, {"nome": "x", "preco": 1}, "preco") == "not_applicable"
    assert propose_missing(container, {"preco": 1}, "nome") == "not_applicable"


def test_every_class_maps_to_one_expected_code() -> None:
    assert {expected_code(name) for name in CLASS_ORDER} == {
        "type",
        "required",
        "range",
        "enum",
        "length",
    }


def test_the_value_is_hidden_from_repr_and_str() -> None:
    found = proposal(Schema(type="string", max_length=3), "too_long")

    assert "aaaa" not in repr(found)
    assert "aaaa" not in str(found)


@pytest.mark.parametrize(
    "schema",
    [
        Schema(type="integer", minimum=-5, maximum=9),
        Schema(type="number", minimum=0.5, maximum=2.5, exclusive_minimum=True),
        Schema(type="string", min_length=3, max_length=40),
        Schema(type="string", enum=("x", "y")),
        Schema(type="integer", enum=(3, 4)),
        Schema(type="boolean"),
    ],
)
def test_no_value_carries_attack_characters_and_all_are_short_ascii(schema: Schema) -> None:
    for name in CLASS_ORDER:
        for in_query in (False, True):
            found = propose(schema, name, in_query=in_query)
            if isinstance(found, Proposal):
                text = str(found.value)
                assert text.isascii()
                assert len(text) <= MAX_VALUE_CHARS
                assert not any(char in text for char in FORBIDDEN_CHARS)


scalar_schemas = st.one_of(
    st.builds(
        Schema,
        type=st.sampled_from(["integer", "number"]),
        minimum=st.one_of(st.none(), st.integers(-50, 50)),
        maximum=st.one_of(st.none(), st.integers(51, 150)),
    ),
    st.builds(
        Schema,
        type=st.just("string"),
        min_length=st.one_of(st.none(), st.integers(0, 5)),
        max_length=st.one_of(st.none(), st.integers(6, 30)),
    ),
    st.builds(
        Schema,
        type=st.just("string"),
        enum=st.lists(
            st.text("abc", min_size=1, max_size=3), min_size=1, max_size=4, unique=True
        ).map(tuple),
    ),
    st.builds(Schema, type=st.just("boolean")),
)


@settings(max_examples=60, deadline=None)
@given(schema=scalar_schemas, in_query=st.booleans())
def test_every_proposed_value_violates_the_schema_with_exactly_the_class_code(
    schema: Schema, in_query: bool
) -> None:
    for name in CLASS_ORDER:
        found = propose(schema, name, in_query=in_query)
        if isinstance(found, Proposal):
            assert check_schema(schema, found.value) == (expected_code(name),)
