import re
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.adapters.datagen import GeneratorCatalogue, build_registry
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.datagen_catalog import generator_names, get_generator, validate_args
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.request_builder import ValueRequest
from tests.unit.adapters.datagen.verifiers import (
    valid_cep,
    valid_cnpj,
    valid_cns,
    valid_cpf,
    valid_phone,
)
from tests.unit.api_helpers import NOW, TAG


def request(
    generator: str,
    *,
    unique: bool = False,
    counter: int = 0,
    draw_index: int = 0,
    schema: Schema | None = None,
    **args: Any,  # argumentos livres do gerador sob teste
) -> ValueRequest:
    full = validate_args(get_generator(generator), args)
    return ValueRequest(
        generator=generator,
        args=full,
        value_schema=schema or Schema(),
        field_path="body.campo",
        field_name="campo",
        location="body",
        operation_id="op",
        unique=unique,
        counter=counter,
        draw_index=draw_index,
        run_tag=TAG,
    )


def draw(seed: int, generator: str, **kwargs: object) -> JsonValue:
    return GeneratorCatalogue(seed, NOW)(request(generator, **kwargs))  # type: ignore[arg-type]


def test_registry_names_are_exactly_the_domain_catalog() -> None:
    assert set(build_registry()) == set(generator_names())


def test_catalogue_rejects_a_naive_clock() -> None:
    with pytest.raises(ConfigError):
        GeneratorCatalogue(1, datetime(2026, 1, 1))  # testa instante sem fuso


def test_catalogue_rejects_a_generator_it_does_not_implement() -> None:
    fake = request("uuid").model_copy(update={"generator": "inventado"})

    with pytest.raises(ConfigError, match="sem implementação"):
        GeneratorCatalogue(1, NOW)(fake)


@pytest.mark.parametrize("name", sorted(generator_names()))
def test_every_generator_is_deterministic_for_the_same_seed(name: str) -> None:
    extra: dict[str, object] = {}
    if name == "numeric":
        extra = {"digits": 6}
    elif name == "choice":
        extra = {"values": ["a", "b", "c", "d"]}
    elif name == "constant":
        extra = {"value": "k"}

    first = [draw(7, name, **extra) for _ in range(1)]
    again = [draw(7, name, **extra) for _ in range(1)]

    assert first == again


def test_a_catalogue_with_the_same_seed_repeats_the_whole_sequence() -> None:
    a, b = GeneratorCatalogue(3, NOW), GeneratorCatalogue(3, NOW)
    requests = [request("alphanumeric"), request("br.cpf"), request("email"), request("uuid")] * 5

    assert [a(r) for r in requests] == [b(r) for r in requests]


def test_different_seeds_give_different_values() -> None:
    assert draw(1, "alphanumeric") != draw(2, "alphanumeric")


def test_numeric_has_the_requested_digits_and_keeps_leading_zeros_possible() -> None:
    values = {str(draw(s, "numeric", digits=3)) for s in range(200)}

    assert all(len(v) == 3 and v.isdigit() for v in values)
    assert any(v.startswith("0") for v in values)


def test_numeric_unique_uses_tag_prefix_and_counter() -> None:
    value = GeneratorCatalogue(1, NOW)(request("numeric", digits=8, unique=True, counter=7))

    assert value == str(0x7F3A % 10**4).zfill(4) + "0007"


def test_integer_stays_within_args_and_schema_defaults() -> None:
    assert 5 <= int(str(draw(1, "integer", min=5, max=9))) <= 9
    schema = Schema(type="integer", minimum=100, maximum=100)
    assert GeneratorCatalogue(1, NOW)(request("integer", schema=schema)) == 100


def test_integer_rejects_args_that_contradict_the_schema() -> None:
    schema = Schema(type="integer", minimum=100, maximum=200)

    with pytest.raises(ConfigError, match="não admitem"):
        GeneratorCatalogue(1, NOW)(request("integer", schema=schema, max=50))


def test_integer_unique_is_distinct_and_fails_when_the_range_is_too_small() -> None:
    catalogue = GeneratorCatalogue(1, NOW)
    values = {
        catalogue(request("integer", unique=True, counter=c, min=1, max=10)) for c in range(10)
    }

    assert len(values) == 10
    with pytest.raises(ConfigError, match="só comporta"):
        catalogue(request("integer", unique=True, counter=10, min=1, max=10))


def test_number_is_rounded_and_within_bounds() -> None:
    value = draw(1, "number", min=1, max=3, decimals=1)

    assert isinstance(value, float)
    assert 1 <= value <= 3
    assert round(value, 1) == value


def test_boolean_returns_both_values_over_many_seeds() -> None:
    assert {draw(s, "boolean") for s in range(40)} == {True, False}


def test_alphanumeric_uses_lowercase_letters_and_digits_with_the_prefix_and_length() -> None:
    value = str(draw(1, "alphanumeric", length=12, prefix="qa"))

    assert len(value) == 12
    assert value.startswith("qa")
    assert re.fullmatch(r"[a-z0-9]+", value)


def test_alphanumeric_default_length_follows_the_schema() -> None:
    schema = Schema(type="string", min_length=20)

    assert len(str(GeneratorCatalogue(1, NOW)(request("alphanumeric", schema=schema)))) == 20
    capped = Schema(type="string", max_length=4)
    assert len(str(GeneratorCatalogue(1, NOW)(request("alphanumeric", schema=capped)))) == 4


def test_alphanumeric_truncates_a_long_prefix_to_the_length() -> None:
    assert draw(1, "alphanumeric", length=3, prefix="abcdef") == "abc"


def test_alphanumeric_unique_embeds_tag_and_counter_after_the_prefix() -> None:
    value = GeneratorCatalogue(1, NOW)(
        request("alphanumeric", unique=True, counter=18, length=14, prefix="hd")
    )

    assert str(value).startswith("hd7f3a0012")
    assert len(str(value)) == 14


def test_alphanumeric_unique_fits_a_short_field_by_cutting_the_tag() -> None:
    value = GeneratorCatalogue(1, NOW)(request("alphanumeric", unique=True, counter=1, length=6))

    assert value == "7f" + "0001"


def test_alphanumeric_unique_fails_when_the_field_cannot_hold_the_counter() -> None:
    with pytest.raises(ConfigError):
        GeneratorCatalogue(1, NOW)(request("alphanumeric", unique=True, length=3))


def test_uuid_is_version_4_and_unique_embeds_tag_and_counter() -> None:
    plain = str(draw(1, "uuid"))
    unique = str(GeneratorCatalogue(1, NOW)(request("uuid", unique=True, counter=255)))

    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", plain
    )
    assert unique.startswith("7f3a0000-00ff-4")


def test_email_uses_the_reserved_test_domain_by_default() -> None:
    assert re.fullmatch(r"hd[a-z0-9]{10}@example\.test", str(draw(1, "email")))


def test_email_unique_embeds_tag_and_counter_and_honours_domain_and_prefix() -> None:
    value = GeneratorCatalogue(1, NOW)(
        request("email", unique=True, counter=3, domain="teste.exemplo.com.br", prefix="qa")
    )

    assert value == "qa7f3a0003@teste.exemplo.com.br"


def test_uri_builds_on_the_base_and_embeds_the_token_when_unique() -> None:
    assert str(draw(1, "uri", base="https://a.test/")).startswith("https://a.test/r/")
    unique = GeneratorCatalogue(1, NOW)(request("uri", unique=True, counter=2))
    assert unique == "https://example.test/r/7f3a0002"


def test_date_is_relative_to_the_injected_clock() -> None:
    value = date.fromisoformat(str(draw(1, "date", min_offset_days=10, max_offset_days=10)))

    assert value == NOW.date() + timedelta(days=10)


def test_date_uses_utc_even_when_the_clock_has_another_zone() -> None:
    late = datetime(2026, 11, 13, 22, 0, tzinfo=timezone(timedelta(hours=-5)))
    value = GeneratorCatalogue(1, late)(request("date", min_offset_days=0, max_offset_days=0))

    assert value == "2026-11-14"


def test_datetime_is_rfc3339_utc_within_the_requested_day() -> None:
    value = str(draw(1, "datetime", min_offset_days=-1, max_offset_days=-1))

    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert parsed.date() == (NOW - timedelta(days=1)).date()


def test_choice_picks_from_the_list_and_requires_it() -> None:
    assert draw(1, "choice", values=["a", "b"]) in {"a", "b"}
    broken = request("choice", values=["a"]).model_copy(update={"args": {}})
    with pytest.raises(ConfigError):
        GeneratorCatalogue(1, NOW)(broken)


def test_constant_returns_the_value_even_when_it_is_null() -> None:
    assert draw(1, "constant", value=None) is None
    assert draw(1, "constant", value=3) == 3


def test_sequence_follows_the_draw_index_with_start_step_and_prefix() -> None:
    catalogue = GeneratorCatalogue(1, NOW)

    assert catalogue(request("sequence", draw_index=3, start=10, step=5)) == 25
    assert catalogue(request("sequence", draw_index=2, prefix="C-")) == "C-3"


def test_cpf_formatted_and_plain_forms_are_valid_and_masked_as_documented() -> None:
    plain, masked = str(draw(1, "br.cpf")), str(draw(1, "br.cpf", formatted=True))

    assert re.fullmatch(r"\d{11}", plain)
    assert re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}", masked)
    assert valid_cpf(plain)
    assert valid_cpf(masked)


def test_cnpj_formatted_has_branch_0001_and_is_valid() -> None:
    masked = str(draw(1, "br.cnpj", formatted=True))

    assert re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/0001-\d{2}", masked)
    assert valid_cnpj(masked)


def test_cns_kinds_start_with_the_documented_digits() -> None:
    assert str(draw(1, "br.cns")).startswith(("1", "2"))
    assert str(draw(1, "br.cns", kind="provisional")).startswith(("7", "8", "9"))


def test_phone_forms_follow_the_documented_masks() -> None:
    assert re.fullmatch(
        r"\+55 \(\d{2}\) 9\d{4}-\d{4}", str(draw(1, "br.phone", formatted=True, country_code=True))
    )
    assert re.fullmatch(
        r"\(\d{2}\) [2-5]\d{3}-\d{4}", str(draw(1, "br.phone", formatted=True, mobile=False))
    )
    assert str(draw(1, "br.phone", ddd=11)).startswith("119")
    assert str(draw(1, "br.phone", country_code=True)).startswith("55")


def test_cep_forms_and_the_all_zero_guard() -> None:
    assert re.fullmatch(r"\d{5}-\d{3}", str(draw(1, "br.cep", formatted=True)))
    zero_tag = ValueRequest(**{**request("br.cep", unique=True).model_dump(), "run_tag": "0000"})
    assert GeneratorCatalogue(1, NOW)(zero_tag) == "10000000"


def test_crm_has_the_documented_shape_and_the_requested_uf() -> None:
    assert re.fullmatch(r"\d{7}-SP", str(draw(1, "br.crm")))
    assert re.fullmatch(r"\d{7}-RJ", str(draw(1, "br.crm", digits=7, uf="RJ")))


def test_crm_unique_differs_between_two_runs_with_different_tags() -> None:
    first = ValueRequest(
        **{**request("br.crm", unique=True, digits=7).model_dump(), "run_tag": "a1b2"}
    )
    second = ValueRequest(
        **{**request("br.crm", unique=True, digits=7).model_dump(), "run_tag": "c3d4"}
    )

    assert GeneratorCatalogue(1, NOW)(first) != GeneratorCatalogue(1, NOW)(second)


def test_crm_rejects_an_unknown_uf() -> None:
    with pytest.raises(ConfigError):
        request("br.crm", uf="XX")


def test_cpf_unique_never_returns_a_repeated_digit_number() -> None:
    zero_tag = ValueRequest(**{**request("br.cpf", unique=True).model_dump(), "run_tag": "0000"})

    value = str(GeneratorCatalogue(1, NOW)(zero_tag))

    assert valid_cpf(value)
    assert value.startswith("1")


def test_cnpj_unique_never_returns_a_repeated_digit_root() -> None:
    zero_tag = ValueRequest(**{**request("br.cnpj", unique=True).model_dump(), "run_tag": "0000"})

    assert valid_cnpj(str(GeneratorCatalogue(1, NOW)(zero_tag)))


UNIQUE_CASES: list[tuple[str, dict[str, Any]]] = [
    ("numeric", {"digits": 6}),
    ("integer", {"min": 1, "max": 100000}),
    ("alphanumeric", {}),
    ("uuid", {}),
    ("email", {}),
    ("uri", {}),
    ("sequence", {}),
    ("br.cpf", {}),
    ("br.cnpj", {}),
    ("br.cns", {}),
    ("br.cns", {"kind": "provisional"}),
    ("br.phone", {}),
    ("br.phone", {"mobile": False}),
    ("br.cep", {}),
    ("br.crm", {}),
    ("br.crm", {"digits": 7, "uf": "RJ"}),
]


@pytest.mark.parametrize(("name", "args"), UNIQUE_CASES)
def test_unique_values_never_repeat_across_thousands_of_draws(
    name: str, args: dict[str, Any]
) -> None:
    catalogue = GeneratorCatalogue(11, NOW)
    seen: set[str] = set()

    for counter in range(5000):
        value = catalogue(request(name, unique=True, counter=counter, draw_index=counter, **args))
        seen.add(repr(value))

    assert len(seen) == 5000


@pytest.mark.parametrize(
    ("name", "args"),
    # sequence repete entre execuções por contrato; integer só é único dentro da execução.
    [case for case in UNIQUE_CASES if case[0] not in {"sequence", "integer"}],
)
def test_unique_values_from_different_runs_differ(name: str, args: dict[str, Any]) -> None:
    first = request(name, unique=True, **args)
    second = ValueRequest(**{**first.model_dump(), "run_tag": "1234"})
    catalogue = GeneratorCatalogue(5, NOW)

    assert catalogue(first) != catalogue(second)


@settings(max_examples=60)
@given(st.integers(min_value=0, max_value=2**31), st.booleans(), st.booleans())
def test_br_documents_always_pass_the_independent_verifiers(
    seed: int, formatted: bool, unique: bool
) -> None:
    catalogue = GeneratorCatalogue(seed, NOW)
    counter = seed % 5000

    def make(name: str, **args: Any) -> str:
        return str(
            catalogue(request(name, unique=unique, counter=counter, formatted=formatted, **args))
        )

    assert valid_cpf(make("br.cpf"))
    assert valid_cnpj(make("br.cnpj"))
    assert valid_cep(make("br.cep"))
    assert valid_phone(make("br.phone"), mobile=True)
    assert valid_phone(make("br.phone", mobile=False), mobile=False)


@settings(max_examples=60)
@given(st.integers(min_value=0, max_value=2**31), st.booleans())
def test_cns_always_passes_the_independent_verifier(seed: int, unique: bool) -> None:
    catalogue = GeneratorCatalogue(seed, NOW)

    for kind in ("definitive", "provisional"):
        value = str(catalogue(request("br.cns", unique=unique, counter=seed % 5000, kind=kind)))
        assert valid_cns(value)
