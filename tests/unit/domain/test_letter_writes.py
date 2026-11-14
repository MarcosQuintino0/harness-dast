"""Carta: `attack.allow_authz_writes` vira `authz.allow_writes` só com a frase da carta."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

TODAY = date(2026, 11, 14)
QUOTE = "Autorizamos o teste de autorização a alterar dados de teste do ambiente."


def _review(data: dict[str, Any]) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", TODAY)


def _letter(allow: dict[str, Any] | None) -> dict[str, Any]:
    data = valid_letter_data()
    data["attack"] = {} if allow is None else {"allow_authz_writes": allow}
    return data


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def _codes(review: LetterReview) -> dict[str, str]:
    return {issue.field: issue.code for issue in review.issues}


def test_the_letter_without_the_field_keeps_writes_off_and_writes_no_authz_block() -> None:
    review = _review(valid_letter_data())

    assert review.ready
    assert review.profile_text is not None
    assert "authz" not in review.profile_text
    assert "authz.allow_writes" not in review.blocks
    assert _profile(review).authz.allow_writes is False
    assert "AUTHZ_WRITES_AUTHORIZED" not in [w.code for w in review.warnings]


@pytest.mark.parametrize(
    "allow",
    [
        {"source": "desconhecido"},
        {"value": None, "source": "pessoa"},
        {"value": False, "source": "carta", "quote": QUOTE},
        {"value": False, "source": "pessoa"},
    ],
)
def test_unknown_null_or_false_answers_keep_writes_off_without_any_pending_item(
    allow: dict[str, Any],
) -> None:
    review = _review(_letter(allow))

    assert review.ready
    assert review.profile_text is not None
    assert "authz" not in review.profile_text
    assert _profile(review).authz.allow_writes is False
    assert review.warnings == () or "AUTHZ_WRITES_AUTHORIZED" not in [
        w.code for w in review.warnings
    ]


def test_true_from_the_letter_with_a_quote_generates_the_block_and_warns() -> None:
    review = _review(_letter(answer(True, "carta", QUOTE)))

    assert review.ready
    assert "authz.allow_writes" in review.blocks
    profile = _profile(review)
    assert profile.authz.allow_writes is True
    assert "AUTHZ_WRITES_AUTHORIZED" in [w.code for w in review.warnings]
    warning = next(w for w in review.warnings if w.code == "AUTHZ_WRITES_AUTHORIZED")
    assert warning.field == "attack.allow_authz_writes"
    assert "ESCREVER" in warning.message


def test_the_generated_block_holds_only_allow_writes_and_the_text_is_deterministic() -> None:
    data = _letter(answer(True, "carta", QUOTE))

    first = _review(data)
    second = _review(data)

    assert first.profile_text == second.profile_text
    assert first.profile_text is not None
    assert "authz:\n  allow_writes: true\n" in first.profile_text


@pytest.mark.parametrize(
    "allow",
    [
        answer(True, "pessoa", QUOTE),
        answer(True, "carta"),
        answer(True, "carta", "   "),
    ],
)
def test_true_without_the_letter_as_source_or_without_a_quote_is_refused(
    allow: dict[str, Any],
) -> None:
    review = _review(_letter(allow))

    assert _codes(review) == {"attack.allow_authz_writes": "AUTHZ_WRITES_NEEDS_LETTER"}
    assert review.profile_text is None
    assert review.warnings == ()


@pytest.mark.parametrize("value", ["sim", "true", 1, "yes", ["x"], {"a": 1}])
def test_a_value_that_is_not_a_boolean_is_refused_and_never_turns_writes_on(value: object) -> None:
    review = _review(_letter(answer(value, "carta", QUOTE)))

    assert _codes(review) == {"attack.allow_authz_writes": "INVALID_VALUE"}
    assert review.profile_text is None


def test_the_refusal_of_a_non_boolean_never_repeats_the_value_received() -> None:
    review = _review(_letter(answer("valor-distintivo-xyz", "carta", QUOTE)))

    assert "valor-distintivo-xyz" not in review.issues[0].message


def test_an_unknown_key_inside_the_attack_section_is_a_shape_error() -> None:
    from harness_dast.domain.errors import ConfigError

    data = valid_letter_data()
    data["attack"] = {"allow_authz_write": answer(True, "carta", QUOTE)}

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_an_answer_without_a_source_is_a_shape_error() -> None:
    from harness_dast.domain.errors import ConfigError

    data = valid_letter_data()
    data["attack"] = {"allow_authz_writes": {"value": True}}

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_a_bare_boolean_in_place_of_the_answer_is_a_shape_error() -> None:
    from harness_dast.domain.errors import ConfigError

    data = valid_letter_data()
    data["attack"] = {"allow_authz_writes": True}

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_a_placeholder_free_gate_failure_still_refuses_before_reading_the_writes_answer() -> None:
    data = _letter(answer(True, "pessoa"))
    data["gates"]["test_environment"] = answer(False)

    review = _review(data)

    assert list(_codes(review)) == ["gates.test_environment"]


def test_the_authorized_letter_text_carries_the_header_note_and_strength_still_works() -> None:
    data = _letter(answer(True, "carta", QUOTE))
    data["attack"]["strength"] = answer("MEDIUM", "pessoa")

    review = _review(data)

    assert review.profile_text is not None
    assert "authz.allow_writes" in review.profile_text.splitlines()[3]
    assert review.blocks[-2:] == ("scan.strength", "authz.allow_writes")
    profile = _profile(review)
    assert profile.scan.strength == "MEDIUM"
    assert profile.authz.allow_writes is True
