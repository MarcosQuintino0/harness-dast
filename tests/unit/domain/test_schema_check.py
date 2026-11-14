import pytest

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.schema_check import check_schema, violations


def check(schema: Schema, value: JsonValue) -> tuple[str, ...]:
    return violations(schema, value)


def test_violations_is_empty_when_value_satisfies_every_constraint() -> None:
    schema = Schema(type="string", min_length=2, max_length=5, pattern="^[a-z]+$")

    assert check(schema, "abc") == ()


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        (Schema(type="string"), 5),
        (Schema(type="integer"), "5"),
        (Schema(type="integer"), True),
        (Schema(type="integer"), 1.5),
        (Schema(type="number"), "1"),
        (Schema(type="boolean"), 1),
        (Schema(type="null"), "x"),
        (Schema(type="object"), "x"),
    ],
)
def test_violations_reports_type_when_value_has_another_type(
    schema: Schema, value: JsonValue
) -> None:
    assert any("tipo" in problem for problem in check(schema, value))


def test_violations_accepts_float_when_type_is_number() -> None:
    assert check(Schema(type="number"), 1.5) == ()


def test_violations_rejects_null_when_schema_is_not_nullable() -> None:
    assert check(Schema(type="string"), None) == ("nulo não permitido",)


def test_violations_accepts_null_when_schema_is_nullable() -> None:
    assert check(Schema(type="string", nullable=True), None) == ()


def test_violations_rejects_value_outside_enum() -> None:
    assert check(Schema(type="string", enum=("a", "b")), "c") == ("fora do enum",)


def test_violations_distinguishes_true_from_one_in_enum() -> None:
    assert check(Schema(enum=(1,)), True) == ("fora do enum",)
    assert check(Schema(enum=(True,)), 1) == ("fora do enum",)


def test_violations_reports_bounds_for_numbers() -> None:
    schema = Schema(type="integer", minimum=3, maximum=5)

    assert check(schema, 2) == ("abaixo do mínimo",)
    assert check(schema, 6) == ("acima do máximo",)
    assert check(schema, 4) == ()


def test_violations_respects_exclusive_bounds() -> None:
    schema = Schema(
        type="integer", minimum=3, maximum=5, exclusive_minimum=True, exclusive_maximum=True
    )

    assert check(schema, 3) == ("abaixo do mínimo",)
    assert check(schema, 5) == ("acima do máximo",)
    assert check(schema, 4) == ()


def test_violations_enforces_int32_range() -> None:
    schema = Schema(type="integer", format="int32")

    assert check(schema, 2**31) == ("fora do intervalo de int32",)
    assert check(schema, 2**31 - 1) == ()


def test_violations_enforces_text_lengths() -> None:
    schema = Schema(type="string", min_length=2, max_length=3)

    assert check(schema, "a") == ("menor que min_length",)
    assert check(schema, "abcd") == ("maior que max_length",)


@pytest.mark.parametrize(
    ("fmt", "good", "bad"),
    [
        ("date", "2026-02-28", "2026-02-30"),
        ("date", "2026-02-28", "28/02/2026"),
        ("date-time", "2026-02-28T10:00:00Z", "2026-02-28T10:00:00"),
        ("date-time", "2026-02-28T10:00:00+00:00", "2026-02-28"),
        ("date-time", "2026-02-28T10:00:00Z", "ontem T lá"),
        ("uuid", "123e4567-e89b-42d3-a456-426614174000", "123e4567"),
        ("email", "a@b.test", "a@b"),
        ("uri", "https://x.test/a", "x.test"),
        ("uri", "https://x.test/a", "https://x.test/a b"),
    ],
)
def test_violations_checks_known_formats(fmt: str, good: str, bad: str) -> None:
    schema = Schema(type="string", format=fmt)

    assert check(schema, good) == ()
    assert check(schema, bad) == (f"fora do formato {fmt}",)


def test_violations_ignores_unknown_formats() -> None:
    assert check(Schema(type="string", format="password"), "x") == ()


def test_violations_checks_supported_pattern() -> None:
    assert check(Schema(type="string", pattern="^[0-9]{3}$"), "12a") == ("não casa com o pattern",)


def test_violations_accepts_value_when_pattern_is_outside_the_safe_subset() -> None:
    assert check(Schema(type="string", pattern="(a|b)+"), "zzz") == ()


def test_violations_accepts_anything_when_schema_has_no_type() -> None:
    assert check(Schema(), "x") == ()
    assert check(Schema(), None) == ()


@pytest.mark.parametrize(
    ("schema", "value", "expected"),
    [
        (Schema(type="integer"), True, ("type",)),
        (Schema(type="number", minimum=2, exclusive_minimum=True), 2, ("range",)),
        (Schema(type="string", min_length=3), "ab", ("length",)),
        (Schema(type="string", enum=("a",)), "segredo", ("enum",)),
        (Schema(type="object", required=("id",)), {}, ("required",)),
        (Schema(type="array", max_items=1), [1, 2], ("length",)),
        (Schema(type="string", nullable=True), None, ()),
        (Schema(type="integer", truncated=True), "qualquer", ()),
    ],
)
def test_checks_restrictions_without_values(
    schema: Schema, value: JsonValue, expected: tuple[str, ...]
) -> None:
    assert check_schema(schema, value) == expected


def test_offline_check_null_still_obeys_enum() -> None:
    assert check_schema(Schema(type="string", nullable=True, enum=("a",)), None) == ("enum",)
    assert check_schema(Schema(type="string", nullable=True, enum=("a", None)), None) == ()
    assert (
        check_schema(Schema(type="string", nullable=True, enum=("a",), enum_allows_null=True), None)
        == ()
    )
    assert check_schema(Schema(type="string", enum=(None,)), None) == ("type",)
