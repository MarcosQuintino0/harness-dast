from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from tests.fakes.letter_data import answer, valid_letter_data


def test_from_data_accepts_the_valid_letter() -> None:
    letter = Letter.from_data(valid_letter_data())

    assert letter.product == "demo"
    assert letter.gates.test_environment is not None
    assert letter.gates.test_environment.source == "carta"


def test_from_data_accepts_a_letter_with_only_the_header() -> None:
    letter = Letter.from_data({"schema_version": 1, "product": "demo"})

    assert letter.scope.allow is None


@pytest.mark.parametrize("data", [None, [], "texto", 3])
def test_from_data_rejects_a_letter_that_is_not_a_map(data: object) -> None:
    with pytest.raises(ConfigError):
        Letter.from_data(data)


@pytest.mark.parametrize("version", [None, 2, 0, "1", True, 1.0])
def test_from_data_rejects_a_missing_or_unsupported_schema_version(version: object) -> None:
    data: dict[str, Any] = {"schema_version": version, "product": "demo"}
    if version is None:
        del data["schema_version"]

    with pytest.raises(ConfigError, match="schema_version"):
        Letter.from_data(data)


def test_from_data_rejects_an_unknown_top_level_field() -> None:
    data = valid_letter_data()
    data["escopo_extra"] = {}

    with pytest.raises(ConfigError, match=r"escopo_extra: campo desconhecido"):
        Letter.from_data(data)


def test_from_data_rejects_an_unknown_field_inside_a_section() -> None:
    data = valid_letter_data()
    data["scope"]["allow_everything"] = answer(True)

    with pytest.raises(ConfigError, match=r"scope.allow_everything: campo desconhecido"):
        Letter.from_data(data)


def test_from_data_rejects_an_unknown_field_inside_an_answer() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"]["extra"] = 1

    with pytest.raises(ConfigError, match=r"limits.requests_per_second.extra"):
        Letter.from_data(data)


@pytest.mark.parametrize(
    "field",
    [
        "gates.test_environment",
        "gates.synthetic_data",
        "gates.authorization_in_force",
        "gates.product_owner",
        "environment.base_url",
        "scope.allow",
        "authorization.reference",
        "authorization.valid_until",
        "authorization.windows",
        "auth.type",
        "auth.accounts",
        "limits.requests_per_second",
    ],
)
def test_from_data_rejects_a_bare_value_where_an_answer_is_expected(field: str) -> None:
    data = valid_letter_data()
    section, name = field.split(".")
    data[section][name] = "valor sem origem"

    with pytest.raises(ConfigError, match=rf"{section}\.{name}"):
        Letter.from_data(data)


def test_from_data_rejects_an_answer_without_source() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = {"value": 5}

    with pytest.raises(ConfigError, match=r"limits.requests_per_second.source"):
        Letter.from_data(data)


@pytest.mark.parametrize("source", ["agente", "", "Carta", None, 1])
def test_from_data_rejects_an_unknown_source(source: object) -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = {"value": 5, "source": source}

    with pytest.raises(ConfigError, match=r"limits.requests_per_second.source"):
        Letter.from_data(data)


def test_from_data_rejects_an_unknown_answer_that_carries_a_value() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = {"value": 5, "source": "desconhecido"}

    with pytest.raises(ConfigError, match=r"limits.requests_per_second"):
        Letter.from_data(data)


def test_from_data_accepts_an_unknown_answer_without_value() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = {"source": "desconhecido"}

    letter = Letter.from_data(data)

    assert letter.limits.requests_per_second is not None
    assert letter.limits.requests_per_second.value is None


def test_from_data_rejects_a_quote_with_control_characters() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"]["quote"] = "linha\x00nula"

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_from_data_rejects_a_quote_that_is_too_long() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"]["quote"] = "x" * 301

    with pytest.raises(ConfigError):
        Letter.from_data(data)


@pytest.mark.parametrize("product", ["Demo", "meu produto", "", "../x", "a" * 41])
def test_from_data_rejects_an_invalid_product_slug(product: str) -> None:
    with pytest.raises(ConfigError, match="product"):
        Letter.from_data({"schema_version": 1, "product": product})


def test_from_data_error_never_repeats_the_received_secret() -> None:
    data = valid_letter_data()
    data["auth"]["accounts"] = {
        "value": "SenhaLiteral-123",
        "source": "carta",
        "extra": "SenhaLiteral-123",
    }

    with pytest.raises(ConfigError) as caught:
        Letter.from_data(data)

    assert "SenhaLiteral-123" not in caught.value.message


def test_from_data_error_uses_the_feminine_form_for_the_letter() -> None:
    data = valid_letter_data()
    data["escopo_extra"] = {}

    with pytest.raises(ConfigError) as caught:
        Letter.from_data(data)

    assert caught.value.message.startswith("Carta inválida (1 problema(s)):")


def test_from_data_unknown_answer_with_value_says_the_answer_cannot_carry_a_value() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = {"value": 5, "source": "desconhecido"}

    with pytest.raises(ConfigError) as caught:
        Letter.from_data(data)

    assert "uma resposta desconhecida não pode ter value" in caught.value.message
