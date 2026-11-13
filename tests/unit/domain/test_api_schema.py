import pytest
from pydantic import ValidationError

from harness_dast.domain.api_schema import (
    Schema,
    effective_type,
    find_property_path,
    flatten_schema,
    split_field_path,
)
from harness_dast.domain.errors import ConfigError


def test_schema_rejects_inverted_range_when_minimum_exceeds_maximum() -> None:
    with pytest.raises(ValidationError):
        Schema(type="integer", minimum=5, maximum=1)


def test_schema_rejects_inverted_lengths_when_min_length_exceeds_max_length() -> None:
    with pytest.raises(ValidationError):
        Schema(type="string", min_length=5, max_length=1)


def test_schema_rejects_inverted_items_when_min_items_exceeds_max_items() -> None:
    with pytest.raises(ValidationError):
        Schema(type="array", min_items=3, max_items=2)


def test_schema_rejects_unknown_field_when_extra_is_given() -> None:
    with pytest.raises(ValidationError):
        Schema.model_validate({"type": "string", "unknown": 1})


def test_schema_is_frozen_when_assigned_after_creation() -> None:
    schema = Schema(type="string")

    with pytest.raises(ValidationError):
        schema.type = "integer"  # type: ignore[misc]  # testa o modelo congelado


def test_effective_type_infers_object_when_only_properties_are_given() -> None:
    assert effective_type(Schema(properties={"a": Schema()})) == "object"


def test_effective_type_infers_array_when_only_items_are_given() -> None:
    assert effective_type(Schema(items=Schema())) == "array"


def test_effective_type_is_none_when_nothing_is_declared() -> None:
    assert effective_type(Schema()) is None


def test_split_field_path_splits_on_dots() -> None:
    assert split_field_path("data.items.0.id") == ("data", "items", "0", "id")


def test_flatten_merges_all_of_with_tighter_limits_and_union_of_fields() -> None:
    left = Schema(
        type="object",
        required=("a",),
        properties={"a": Schema(type="string", min_length=2, max_length=10)},
    )
    right = Schema(
        type="object",
        required=("b",),
        properties={
            "a": Schema(type="string", min_length=4, max_length=8),
            "b": Schema(type="integer"),
        },
    )

    flat = flatten_schema(Schema(all_of=(left, right)))

    assert flat.required == ("a", "b")
    assert set(flat.properties) == {"a", "b"}
    merged_a = flatten_schema(flat.properties["a"])
    assert (merged_a.min_length, merged_a.max_length) == (4, 8)


def test_flatten_intersects_enums_when_all_of_has_two_enums() -> None:
    first = Schema(type="string", enum=("a", "b", "c"))
    second = Schema(enum=("b", "c", "d"))

    assert flatten_schema(Schema(all_of=(first, second))).enum == ("b", "c")


def test_flatten_takes_stricter_bounds_when_all_of_has_two_ranges() -> None:
    flat = flatten_schema(
        Schema(
            all_of=(
                Schema(type="integer", minimum=1, maximum=100, exclusive_minimum=True),
                Schema(minimum=5, maximum=50),
            )
        )
    )

    assert (flat.minimum, flat.maximum, flat.exclusive_minimum) == (5, 50, True)


def test_flatten_picks_first_non_null_branch_when_one_of_starts_with_null() -> None:
    flat = flatten_schema(
        Schema(one_of=(Schema(type="null"), Schema(type="string", format="uuid")))
    )

    assert (flat.type, flat.format) == ("string", "uuid")


def test_flatten_uses_any_of_when_one_of_is_absent() -> None:
    flat = flatten_schema(Schema(any_of=(Schema(type="integer"),)))

    assert flat.type == "integer"


def test_flatten_returns_base_when_only_null_branches_exist() -> None:
    flat = flatten_schema(Schema(type="string", one_of=(Schema(type="null"),)))

    assert flat.type == "string"


def test_flatten_merges_items_of_both_sides_when_all_of_has_two_arrays() -> None:
    flat = flatten_schema(
        Schema(
            all_of=(
                Schema(type="array", items=Schema(type="integer", minimum=1)),
                Schema(items=Schema(maximum=9)),
            )
        )
    )

    assert flat.items is not None
    inner = flatten_schema(flat.items)
    assert (inner.minimum, inner.maximum) == (1, 9)


def test_flatten_takes_items_from_the_right_when_left_has_none() -> None:
    flat = flatten_schema(
        Schema(all_of=(Schema(type="array"), Schema(items=Schema(type="string"))))
    )

    assert flat.items is not None


def test_flatten_raises_config_error_when_all_of_is_contradictory() -> None:
    contradictory = Schema(all_of=(Schema(type="integer", minimum=10), Schema(maximum=1)))

    with pytest.raises(ConfigError, match="contradit"):
        flatten_schema(contradictory)


def test_find_property_path_follows_properties_and_array_indexes() -> None:
    schema = Schema(
        type="object",
        properties={
            "items": Schema(
                type="array",
                items=Schema(type="object", properties={"id": Schema(type="integer")}),
            )
        },
    )

    found = find_property_path(schema, ("items", "0", "id"))

    assert found is not None
    assert found.type == "integer"


def test_find_property_path_returns_none_when_field_is_missing() -> None:
    assert find_property_path(Schema(type="object"), ("nope",)) is None


def test_find_property_path_accepts_the_rest_when_node_is_truncated() -> None:
    schema = Schema(type="object", properties={"next": Schema(truncated=True)})

    found = find_property_path(schema, ("next", "x", "y"))

    assert found is not None
    assert found.truncated


def test_find_property_path_resolves_through_composition() -> None:
    schema = Schema(all_of=(Schema(type="object", properties={"id": Schema(type="string")}),))

    assert find_property_path(schema, ("id",)) is not None


def test_flatten_raises_config_error_when_all_of_mixes_incompatible_types() -> None:
    with pytest.raises(ConfigError, match="incompatíveis"):
        flatten_schema(Schema(all_of=(Schema(type="boolean"), Schema(type="integer"))))


def test_flatten_narrows_number_and_integer_to_integer_in_all_of() -> None:
    flat = flatten_schema(Schema(all_of=(Schema(type="number"), Schema(type="integer"))))

    assert flat.type == "integer"


@pytest.mark.parametrize("field", ["format", "pattern"])
def test_flatten_raises_config_error_when_all_of_has_different_formats_or_patterns(
    field: str,
) -> None:
    first, second = Schema(**{field: "a"}), Schema(**{field: "b"})  # type: ignore[arg-type]  # campos de texto

    with pytest.raises(ConfigError, match="diferentes"):
        flatten_schema(Schema(all_of=(first, second)))


def test_flatten_accepts_the_same_format_twice_in_all_of() -> None:
    flat = flatten_schema(
        Schema(all_of=(Schema(format="uuid"), Schema(format="uuid", type="string")))
    )

    assert flat.format == "uuid"
