"""Carta: `attack.include_outcomes` vira `scan.include_outcomes` (ADR 0050)."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

TODAY = date(2026, 11, 14)


def _review(data: dict[str, Any]) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", TODAY)


def _letter(outcomes: dict[str, Any] | None, **attack: Any) -> dict[str, Any]:
    data = valid_letter_data()
    data["attack"] = dict(attack)
    if outcomes is not None:
        data["attack"]["include_outcomes"] = outcomes
    return data


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def _codes(review: LetterReview) -> dict[str, str]:
    return {issue.field: issue.code for issue in review.issues}


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"source": "desconhecido"},
        {"value": None, "source": "pessoa"},
        answer([], "carta"),
        answer([], "pessoa"),
    ],
)
def test_absent_null_unknown_or_empty_means_no_extra_class_and_no_pending_item(
    value: dict[str, Any] | None,
) -> None:
    review = _review(_letter(value))

    assert review.ready
    assert review.profile_text is not None
    assert "include_outcomes" not in review.profile_text
    assert "scan.include_outcomes" not in review.blocks
    assert _profile(review).scan.include_outcomes == ()
    assert "OUTCOMES_ATTACK_EXTENDED" not in [w.code for w in review.warnings]


@pytest.mark.parametrize("source", ["carta", "pessoa"])
def test_a_valid_list_from_the_letter_or_from_a_person_needs_no_quote(source: str) -> None:
    review = _review(_letter(answer(["not_found", "validation_error"], source)))

    assert review.ready
    assert _profile(review).scan.include_outcomes == ("validation_error", "not_found")
    assert "scan.include_outcomes" in review.blocks


def test_the_generated_file_names_the_block_and_the_warning_lists_the_classes() -> None:
    review = _review(_letter(answer(["not_found"])))

    assert review.profile_text is not None
    assert "(ADR 0050): scan.include_outcomes" in review.profile_text
    warning = next(w for w in review.warnings if w.code == "OUTCOMES_ATTACK_EXTENDED")
    assert warning.field == "attack.include_outcomes"
    assert "not_found" in warning.message
    assert "POST, PUT e PATCH" in warning.message


def test_a_repeated_class_is_deduplicated_in_the_closed_list_order() -> None:
    review = _review(_letter(answer(["not_found", "conflict", "not_found"])))

    assert _profile(review).scan.include_outcomes == ("conflict", "not_found")


@pytest.mark.parametrize(
    "value",
    [
        ["auth_error"],
        ["server_error"],
        ["success"],
        ["NOT_FOUND"],
        [""],
        ["not_found", "outra"],
        "not_found",
        "sim",
        True,
        3,
        {"not_found": True},
        [3],
        [None],
        [["not_found"]],
    ],
)
def test_an_invalid_value_is_refused_and_the_message_does_not_repeat_it(value: object) -> None:
    review = _review(_letter(answer(value)))

    assert _codes(review) == {"attack.include_outcomes": "INVALID_VALUE"}
    assert review.profile_text is None
    message = review.issues[0].message
    assert "outra" not in message
    assert "not_found" in message  # a lista das cinco classes
    assert "auth_error" not in message


def test_only_the_include_outcomes_block_without_strength_is_listed_exactly() -> None:
    review = _review(_letter(answer(["not_found"])))

    assert "scan.include_outcomes" in review.blocks
    assert "scan.strength" not in review.blocks


def test_only_strength_lists_only_the_strength_block() -> None:
    review = _review(_letter(None, strength=answer("MEDIUM")))

    assert "scan.strength" in review.blocks
    assert "scan.include_outcomes" not in review.blocks


def test_strength_and_outcomes_together_generate_one_scan_block_with_both() -> None:
    review = _review(_letter(answer(["conflict"]), strength=answer("HIGH")))

    profile = _profile(review)
    assert profile.scan.strength == "HIGH"
    assert profile.scan.include_outcomes == ("conflict",)
    assert {"scan.strength", "scan.include_outcomes"} <= set(review.blocks)


def test_a_letter_without_the_field_generates_the_same_text_as_before() -> None:
    review = _review(valid_letter_data())

    assert review.profile_text is not None
    assert "\nscan:" not in review.profile_text
    assert "ADR 0050" not in review.profile_text
    assert review.blocks == ("environment", "openapi", "scope", "limits", "auth")


def test_the_generated_text_is_deterministic() -> None:
    data = _letter(answer(["not_found", "conflict"]))

    assert _review(data).profile_text == _review(data).profile_text
