"""QA independente (V1.5c): perfil e carta com tipos errados, valores enormes e texto hostil."""

import copy
from datetime import date
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter
from harness_dast.domain.negative_config import NegativeConfig
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data
from tests.fakes.profile_data import valid_profile_data

TODAY = date(2026, 11, 14)
QUOTE = "Autorizamos exatamente isto no ambiente de teste."


def _profile(**blocks: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data.update(blocks)
    return ProductProfile.from_data(data)


@pytest.mark.parametrize(
    "negative",
    [
        {"allow_writes": "true"},
        {"allow_writes": 1},
        {"allow_writes": "yes"},
        {"allow_writes": None},
        {"allow_writes": [True]},
        {"max_requests": "5"},
        {"max_requests": 5.5},
        {"max_requests": True},
        {"max_requests": 0},
        {"max_requests": -1},
        {"max_requests": 1001},
        {"max_requests": 10**30},
        {"max_requests": float("inf")},
        {"max_requests": float("nan")},
        {"max_cases_per_operation": 0},
        {"max_cases_per_operation": 21},
        {"max_cases_per_operation": "6"},
        {"max_cases_per_operation": False},
        {"disabled_classes": "wrong_type"},
        {"disabled_classes": ["nope"]},
        {"disabled_classes": ["wrong_type", "wrong_type"]},
        {"disabled_classes": [["wrong_type"]]},
        {"disabled_classes": [None]},
        {"disabled_classes": ["wrong_type"] * 100},
        {"allow_deletes": True},
        {"allow_writes": True, "delete": True},
        {"": True},
        {"allow_writes​": True},
    ],
)
def test_a_malformed_negative_block_is_a_config_error_and_never_enables_writes(
    negative: dict[str, Any],
) -> None:
    with pytest.raises(ConfigError):
        _profile(negative=negative)


@pytest.mark.parametrize("negative", ["", "sim", 1, True, [], [True], "allow_writes"])
def test_a_negative_block_that_is_not_a_mapping_is_a_config_error(negative: Any) -> None:
    with pytest.raises(ConfigError):
        _profile(negative=negative)


@pytest.mark.parametrize(
    "scan",
    [
        {"allow_upload_scan": "true"},
        {"allow_upload_scan": 1},
        {"allow_upload_scan": None},
        {"include_outcomes": "not_found"},
        {"include_outcomes": ["server_error"]},
        {"include_outcomes": ["success"]},
        {"include_outcomes": ["auth_error"]},
        {"include_outcomes": ["not_found", "not_found"]},
        {"include_outcomes": [1]},
        {"include_outcomes": [None]},
        {"include_outcomes": ["not_found"] * 6},
        {"include_outcomes": ["NOT_FOUND"]},
        {"include_outcomes": [" not_found"]},
        {"include_outcomes": ["not_found\n"]},
        {"include_outcomes": {"not_found": True}},
    ],
)
def test_a_malformed_scan_key_is_a_config_error_and_never_widens_the_attack(
    scan: dict[str, Any],
) -> None:
    with pytest.raises(ConfigError):
        _profile(scan=scan)


def test_the_error_message_for_a_hostile_value_never_echoes_it() -> None:
    hostile = "token-segredo-vaza-aqui-123"
    with pytest.raises(ConfigError) as error:
        _profile(negative={"max_requests": hostile, "disabled_classes": [hostile]})

    assert hostile not in str(error.value)
    assert hostile not in error.value.message


def test_the_default_negative_config_is_read_only_and_bounded() -> None:
    config = NegativeConfig()

    assert config.allow_writes is False
    assert config.max_requests <= 1000
    assert config.is_default() is True
    for asked in (None, 1, config.max_requests):
        assert config.effective_max_requests(asked) <= config.max_requests


def _letter(**attack: Any) -> dict[str, Any]:
    data = valid_letter_data()
    data["attack"] = attack
    return data


def _review(data: dict[str, Any]) -> Any:
    return review_letter(Letter.from_data(data), "demo", TODAY)


@pytest.mark.parametrize(
    "response",
    [
        answer("true", "carta", QUOTE),
        answer("sim", "carta", QUOTE),
        answer(1, "carta", QUOTE),
        answer("True", "pessoa", QUOTE),
        answer([True], "carta", QUOTE),
        answer({"v": True}, "carta", QUOTE),
        answer(True, "carta"),
        answer(True, "carta", "   "),
        answer(True, "carta", ""),
        answer(True, "pessoa", QUOTE),
        answer(True, "pessoa"),
    ],
)
@pytest.mark.parametrize("field", ["allow_invalid_input_writes", "allow_upload_scan"])
def test_a_permission_that_is_not_a_true_boolean_from_the_letter_with_a_quote_is_never_granted(
    field: str, response: dict[str, Any]
) -> None:
    review = _review(_letter(**{field: response}))

    if review.profile_text is not None:
        from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml

        profile = ProductProfile.from_data(parse_profile_yaml(review.profile_text))
        assert profile.negative.allow_writes is False
        assert profile.scan.allow_upload_scan is False


@pytest.mark.parametrize(
    "value",
    [
        "not_found",
        ["not_found", "nope"],
        ["server_error"],
        ["not_found", 1],
        [None],
        [["not_found"]],
        {"not_found": True},
        ["NOT_FOUND"],
        ["not_found​"],
        "x" * 100_000,
        ["x" * 100_000],
        ["not_found"] * 10_000,
    ],
)
def test_include_outcomes_in_the_letter_never_accepts_text_or_unknown_classes(value: Any) -> None:
    review = _review(_letter(include_outcomes=answer(value, "carta")))

    codes = [issue.code for issue in review.issues]
    if (
        isinstance(value, list)
        and all(isinstance(i, str) for i in value)
        and set(value) == {"not_found"}
    ):
        assert review.profile_text is not None
        return
    assert "INVALID_VALUE" in codes
    assert not review.ready or "include_outcomes" not in (review.profile_text or "")


def test_include_outcomes_accepts_person_or_letter_and_dedupes_in_closed_order() -> None:
    review = _review(
        _letter(include_outcomes=answer(["not_found", "conflict", "not_found"], "pessoa"))
    )

    assert review.ready
    assert review.profile_text is not None
    assert review.profile_text.index("conflict") < review.profile_text.index("not_found")


def test_a_quote_with_control_characters_or_enormous_size_is_refused_by_the_letter() -> None:
    for quote in ("x\x00y", "a\u0007b", "linha\nquebrada", "z" * 100_000):
        with pytest.raises(ConfigError):
            Letter.from_data(_letter(allow_upload_scan=answer(True, "carta", quote)))
