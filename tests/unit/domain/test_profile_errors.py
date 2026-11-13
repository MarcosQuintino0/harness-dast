import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from harness_dast.domain.profile_errors import to_config_error

LITERAL = "valor-que-nao-pode-vazar"


class Inner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class Outer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[Inner, ...]
    count: int


def validation_error(data: dict[str, object]) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        Outer.model_validate(data)
    return caught.value


def test_to_config_error_lists_each_problem_with_field_path_when_several_fail() -> None:
    error = validation_error({"items": [{"name": 1}, {}], "count": "x", "extra": 1})

    result = to_config_error(error, hint="Corrija.")

    assert "items[0].name: " in result.message
    assert "items[1].name: campo obrigatório ausente" in result.message
    assert "count: " in result.message
    assert "extra: campo desconhecido" in result.message
    assert result.hint == "Corrija."


def test_to_config_error_never_echoes_received_values_when_types_are_wrong() -> None:
    error = validation_error({"items": [{"name": LITERAL, "oops": LITERAL}], "count": LITERAL})

    result = to_config_error(error, hint="Corrija.")

    assert LITERAL not in result.message


def test_to_config_error_deduplicates_problems_when_the_same_one_repeats() -> None:
    error = validation_error({"items": [], "count": "a"})

    result = to_config_error(error, hint="h")

    assert result.message.count("count:") == 1


def test_to_config_error_uses_generic_name_when_error_is_at_the_root() -> None:
    with pytest.raises(ValidationError) as caught:
        Inner.model_validate("não é um mapa")

    result = to_config_error(caught.value, hint="h")

    assert "(perfil): " in result.message
