import pytest

from harness_dast.domain.datagen_catalog import (
    BR_DDD_CODES,
    CATALOG,
    generator_names,
    get_generator,
    validate_args,
)
from harness_dast.domain.errors import ConfigError


def test_catalog_has_unique_names() -> None:
    names = generator_names()

    assert len(set(names)) == len(names)


def test_catalog_contains_the_documented_generators() -> None:
    expected = {
        "numeric", "integer", "number", "boolean", "alphanumeric", "uuid", "email", "uri",
        "date", "datetime", "choice", "constant", "sequence",
        "br.cpf", "br.cnpj", "br.cns", "br.phone", "br.cep", "br.crm",
    }  # fmt: skip

    assert set(generator_names()) == expected


def test_ddd_codes_are_valid_two_digit_area_codes() -> None:
    assert all(11 <= code <= 99 for code in BR_DDD_CODES)
    assert 11 in BR_DDD_CODES
    assert 21 in BR_DDD_CODES
    assert 10 not in BR_DDD_CODES
    assert len(set(BR_DDD_CODES)) == len(BR_DDD_CODES)


def test_get_generator_raises_with_the_list_of_names_when_unknown() -> None:
    with pytest.raises(ConfigError) as caught:
        get_generator("br.rg")

    assert "br.cpf" in caught.value.message
    assert "br.rg" not in caught.value.message


def test_validate_args_applies_defaults() -> None:
    args = validate_args(get_generator("email"), {})

    assert args == {"domain": "example.test", "prefix": "hd"}


def test_validate_args_keeps_given_values() -> None:
    args = validate_args(get_generator("numeric"), {"digits": 8})

    assert args == {"digits": 8}


def test_validate_args_requires_required_arguments() -> None:
    with pytest.raises(ConfigError, match="exige o argumento 'digits'"):
        validate_args(get_generator("numeric"), {})


def test_validate_args_rejects_unknown_arguments_without_echoing_long_text() -> None:
    with pytest.raises(ConfigError) as caught:
        validate_args(get_generator("numeric"), {"digits": 3, "x\ny": 1})

    assert "'x?y'" in caught.value.message
    assert "digits" in (caught.value.hint or "")


def test_validate_args_rejects_unknown_arguments_for_generators_without_args() -> None:
    with pytest.raises(ConfigError):
        validate_args(get_generator("uuid"), {"a": 1})


@pytest.mark.parametrize(
    ("generator", "args"),
    [
        ("numeric", {"digits": "8"}),
        ("numeric", {"digits": True}),
        ("numeric", {"digits": 8.0}),
        ("numeric", {"digits": 0}),
        ("numeric", {"digits": 31}),
        ("br.cpf", {"formatted": "yes"}),
        ("br.cpf", {"formatted": 1}),
        ("email", {"domain": 3}),
        ("email", {"domain": "x" * 1001}),
        ("choice", {"values": []}),
        ("choice", {"values": "a"}),
        ("choice", {"values": [{"a": 1}]}),
        ("choice", {"values": ["a"] * 201}),
        ("constant", {"value": {"a": 1}}),
        ("constant", {"value": "x" * 1001}),
        ("br.cns", {"kind": "outro"}),
        ("br.phone", {"ddd": 10}),
        ("sequence", {"step": 0}),
        ("date", {"min_offset_days": 5, "max_offset_days": 1}),
        ("integer", {"min": 9, "max": 1}),
    ],
)
def test_validate_args_rejects_invalid_values(generator: str, args: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        validate_args(get_generator(generator), args)


def test_validate_args_never_echoes_the_received_value() -> None:
    with pytest.raises(ConfigError) as caught:
        validate_args(get_generator("numeric"), {"digits": "SEGREDO-123"})

    assert "SEGREDO" not in caught.value.message


def test_validate_args_accepts_scalars_and_lists() -> None:
    assert validate_args(get_generator("choice"), {"values": ["a", 1, None, True, 1.5]})
    assert validate_args(get_generator("constant"), {"value": None}) == {"value": None}


def test_every_unique_generator_declares_support_and_the_rest_do_not() -> None:
    not_unique = {d.name for d in CATALOG if not d.supports_unique}

    assert not_unique == {"number", "boolean", "date", "datetime", "choice", "constant"}
