import pytest

from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.implicit_values import (
    FieldNotGeneratable,
    implicit_draw,
    numeric_bounds,
)


def draw(schema: Schema, schema_type: str | None = None) -> tuple[str, dict[str, object]]:
    generator, args = implicit_draw(schema, schema_type or schema.type, "campo")
    return generator, dict(args)


def test_field_not_generatable_is_a_config_error() -> None:
    assert issubclass(FieldNotGeneratable, ConfigError)


def test_implicit_draw_uses_boolean_for_booleans() -> None:
    assert draw(Schema(type="boolean")) == ("boolean", {})


def test_implicit_draw_uses_wide_default_range_for_unbounded_integers() -> None:
    generator, args = draw(Schema(type="integer"))

    assert generator == "integer"
    assert args == {"min": 1, "max": 100_001}


def test_implicit_draw_respects_integer_bounds_and_exclusivity() -> None:
    schema = Schema(
        type="integer", minimum=10, maximum=20, exclusive_minimum=True, exclusive_maximum=True
    )

    assert draw(schema)[1] == {"min": 11, "max": 19}


def test_implicit_draw_rounds_fractional_bounds_inwards() -> None:
    assert draw(Schema(type="number", minimum=0.5, maximum=4.5))[1] == {"min": 1, "max": 4}


def test_implicit_draw_uses_number_generator_for_numbers() -> None:
    assert draw(Schema(type="number"))[0] == "number"


def test_implicit_draw_clamps_to_int32_range() -> None:
    _, args = draw(Schema(type="integer", format="int32", minimum=2**31 - 5))

    assert args == {"min": 2**31 - 5, "max": 2**31 - 1}


def test_implicit_draw_uses_a_negative_range_when_only_a_negative_maximum_is_given() -> None:
    _, args = draw(Schema(type="integer", maximum=-5))

    assert args == {"min": -1005, "max": -5}


def test_implicit_draw_fails_when_no_integer_fits_the_bounds() -> None:
    with pytest.raises(FieldNotGeneratable, match="'campo'"):
        draw(Schema(type="integer", minimum=1.2, maximum=1.8))


def test_numeric_bounds_is_public_and_returns_the_admitted_interval() -> None:
    assert numeric_bounds(Schema(type="integer", minimum=3, maximum=9), "x") == (3, 9)


@pytest.mark.parametrize(
    ("fmt", "generator"),
    [
        ("uuid", "uuid"),
        ("email", "email"),
        ("uri", "uri"),
        ("url", "uri"),
        ("date", "date"),
        ("date-time", "datetime"),
    ],
)
def test_implicit_draw_maps_string_formats_to_generators(fmt: str, generator: str) -> None:
    assert draw(Schema(type="string", format=fmt)) == (generator, {})


def test_implicit_draw_uses_reserved_documentation_values_for_ip_and_hostname() -> None:
    assert draw(Schema(type="string", format="ipv4")) == ("constant", {"value": "192.0.2.10"})
    assert draw(Schema(type="string", format="hostname"))[1] == {"value": "host.example.test"}


def test_implicit_draw_treats_untyped_schemas_as_text() -> None:
    assert draw(Schema(), None) == ("alphanumeric", {"length": 10})


def test_implicit_draw_fits_text_length_between_min_and_max() -> None:
    assert draw(Schema(type="string", min_length=15))[1] == {"length": 15}
    assert draw(Schema(type="string", max_length=4))[1] == {"length": 4}
    assert draw(Schema(type="string", min_length=2, max_length=30))[1] == {"length": 10}


def test_implicit_draw_returns_empty_text_when_max_length_is_zero() -> None:
    assert draw(Schema(type="string", max_length=0)) == ("constant", {"value": ""})


def test_implicit_draw_fails_when_text_must_be_longer_than_256() -> None:
    with pytest.raises(FieldNotGeneratable, match="256"):
        draw(Schema(type="string", min_length=300))


def test_implicit_draw_synthesizes_text_from_a_simple_pattern() -> None:
    assert draw(Schema(type="string", pattern="^[A-Z]{3}[0-9]{2}$")) == (
        "constant",
        {"value": "AAA00"},
    )


def test_implicit_draw_fails_with_instruction_when_pattern_is_complex() -> None:
    with pytest.raises(FieldNotGeneratable) as caught:
        draw(Schema(type="string", pattern="(a|b)+"))

    assert "regra" in (caught.value.hint or "")


def test_implicit_draw_fails_when_pattern_and_lengths_conflict() -> None:
    with pytest.raises(FieldNotGeneratable, match="Não há valor"):
        draw(Schema(type="string", pattern="^[a-z]{5}$", max_length=3))


def test_implicit_draw_fails_when_synthesized_text_exceeds_the_argument_limit() -> None:
    with pytest.raises(FieldNotGeneratable):
        draw(Schema(type="string", pattern="^a{256}b{256}c{256}d{256}e{256}$"))
