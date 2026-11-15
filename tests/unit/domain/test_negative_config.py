"""Bloco `negative` do perfil: padrões, faixas e entrada malformada (ADR 0051)."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.negative_config import NegativeConfig
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def profile_with(block: Any) -> dict[str, Any]:
    data = valid_profile_data()
    data["negative"] = block
    return data


def test_a_profile_without_the_block_uses_the_conservative_defaults() -> None:
    profile = ProductProfile.from_data(valid_profile_data())

    assert profile.negative == NegativeConfig()
    assert profile.negative.allow_writes is False
    assert profile.negative.max_cases_per_operation == 6
    assert profile.negative.max_requests == 200
    assert profile.negative.disabled_classes == ()
    assert profile.negative.is_default()


def test_every_field_can_be_set_inside_its_range() -> None:
    profile = ProductProfile.from_data(
        profile_with(
            {
                "allow_writes": True,
                "max_cases_per_operation": 20,
                "max_requests": 1000,
                "disabled_classes": ["too_long", "too_short"],
            }
        )
    )

    assert profile.negative.allow_writes is True
    assert profile.negative.max_requests == 1000
    assert profile.negative.disabled_classes == ("too_long", "too_short")
    assert not profile.negative.is_default()


@pytest.mark.parametrize(
    ("block", "path"),
    [
        ({"max_requests": 0}, "negative.max_requests"),
        ({"max_requests": 1001}, "negative.max_requests"),
        ({"max_requests": -5}, "negative.max_requests"),
        ({"max_cases_per_operation": 0}, "negative.max_cases_per_operation"),
        ({"max_cases_per_operation": 21}, "negative.max_cases_per_operation"),
        ({"max_requests": "50"}, "negative.max_requests"),
        ({"max_requests": 50.5}, "negative.max_requests"),
        ({"max_requests": True}, "negative.max_requests"),
        ({"max_requests": None}, "negative.max_requests"),
        ({"allow_writes": "true"}, "negative.allow_writes"),
        ({"allow_writes": 1}, "negative.allow_writes"),
        ({"allow_writes": None}, "negative.allow_writes"),
        ({"disabled_classes": ["inventada"]}, "negative.disabled_classes"),
        ({"disabled_classes": ["too_long", "too_long"]}, "negative.disabled_classes"),
        ({"disabled_classes": "too_long"}, "negative.disabled_classes"),
        ({"disabled_classes": [1]}, "negative.disabled_classes"),
        ({"campo_novo": 1}, "negative.campo_novo"),
    ],
)
def test_an_invalid_field_is_a_config_error_naming_the_path(
    block: dict[str, Any], path: str
) -> None:
    with pytest.raises(ConfigError) as error:
        ProductProfile.from_data(profile_with(block))

    assert path in error.value.message


@pytest.mark.parametrize("block", [5, "texto", ["a"], None, True])
def test_a_block_that_is_not_a_map_is_a_config_error(block: Any) -> None:
    with pytest.raises(ConfigError, match="negative"):
        ProductProfile.from_data(profile_with(block))


def test_more_than_seven_classes_are_refused() -> None:
    classes = [
        "wrong_type",
        "missing_required",
        "below_minimum",
        "above_maximum",
        "not_in_enum",
        "too_long",
        "too_short",
        "too_short",
    ]

    with pytest.raises(ConfigError):
        ProductProfile.from_data(profile_with({"disabled_classes": classes}))


def test_the_error_message_never_repeats_the_value_that_was_typed() -> None:
    with pytest.raises(ConfigError) as error:
        ProductProfile.from_data(profile_with({"max_requests": "senha-digitada-por-engano"}))

    assert "senha-digitada-por-engano" not in error.value.message
    assert "senha-digitada-por-engano" not in (error.value.hint or "")


def test_the_model_is_frozen() -> None:
    config = NegativeConfig()

    with pytest.raises(ValidationError):
        config.allow_writes = True  # type: ignore[misc]  # prova que o modelo é congelado


def test_the_request_flag_only_lowers_the_ceiling() -> None:
    config = NegativeConfig(max_requests=50)

    assert config.effective_max_requests(None) == 50
    assert config.effective_max_requests(10) == 10
    assert config.effective_max_requests(50) == 50
    for asked in (0, -1, 51):
        with pytest.raises(ConfigError, match="max-requests"):
            config.effective_max_requests(asked)
