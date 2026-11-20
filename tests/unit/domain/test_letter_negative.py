"""Carta: `attack.allow_invalid_input_writes` vira `negative.allow_writes` só com a carta."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

TODAY = date(2026, 11, 14)
QUOTE = "Autorizamos gravar dado com valor inválido no ambiente de teste."
FIELD = "attack.allow_invalid_input_writes"


def _review(data: dict[str, Any]) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", TODAY)


def _letter(allow: dict[str, Any] | None, **attack: Any) -> dict[str, Any]:
    data = valid_letter_data()
    data["attack"] = dict(attack)
    if allow is not None:
        data["attack"]["allow_invalid_input_writes"] = allow
    return data


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def _codes(review: LetterReview) -> dict[str, str]:
    return {issue.field: issue.code for issue in review.issues}


def test_a_letter_without_the_field_generates_the_same_profile_as_before_byte_for_byte() -> None:
    plain = _review(valid_letter_data())
    empty_attack = _review(_letter(None))

    assert plain.ready
    assert plain.profile_text == empty_attack.profile_text
    assert plain.profile_text is not None
    assert "negative" not in plain.profile_text
    assert "negative.allow_writes" not in plain.blocks
    assert _profile(plain).negative.allow_writes is False
    assert "NEGATIVE_WRITES_AUTHORIZED" not in [w.code for w in plain.warnings]


@pytest.mark.parametrize(
    "allow",
    [
        {"source": "desconhecido"},
        {"value": None, "source": "pessoa"},
        {"value": False, "source": "carta", "quote": QUOTE},
        {"value": False, "source": "pessoa"},
    ],
)
def test_unknown_null_or_false_keeps_writes_off_without_any_pending_item(
    allow: dict[str, Any],
) -> None:
    review = _review(_letter(allow))

    assert review.ready
    assert review.profile_text is not None
    assert "negative" not in review.profile_text
    assert _profile(review).negative.allow_writes is False
    assert "NEGATIVE_WRITES_AUTHORIZED" not in [w.code for w in review.warnings]


def test_true_from_the_letter_with_a_quote_generates_the_block_and_warns() -> None:
    review = _review(_letter(answer(True, "carta", QUOTE)))

    assert review.ready
    assert "negative.allow_writes" in review.blocks
    assert _profile(review).negative.allow_writes is True
    warning = next(w for w in review.warnings if w.code == "NEGATIVE_WRITES_AUTHORIZED")
    assert warning.field == FIELD
    assert "GRAVAR" in warning.message


def test_the_generated_block_holds_only_allow_writes_and_the_text_is_deterministic() -> None:
    data = _letter(answer(True, "carta", QUOTE))

    first = _review(data)
    second = _review(data)

    assert first.profile_text == second.profile_text
    assert first.profile_text is not None
    assert "negative:\n  allow_writes: true\n" in first.profile_text
    assert "(ADR 0051): negative.allow_writes" in first.profile_text
    assert _profile(first).negative == _profile(first).negative.model_copy(
        update={"allow_writes": True}
    )


def test_the_two_write_permissions_are_independent() -> None:
    only_negative = _review(_letter(answer(True, "carta", QUOTE)))
    only_authz = _review(_letter(None, allow_authz_writes=answer(True, "carta", QUOTE)))

    assert _profile(only_negative).authz.allow_writes is False
    assert _profile(only_authz).negative.allow_writes is False
    assert _profile(only_authz).authz.allow_writes is True


@pytest.mark.parametrize(
    "allow",
    [answer(True, "pessoa", QUOTE), answer(True, "carta"), answer(True, "carta", "   ")],
)
def test_true_without_the_letter_as_source_or_without_a_quote_is_refused(
    allow: dict[str, Any],
) -> None:
    review = _review(_letter(allow))

    assert _codes(review) == {FIELD: "NEGATIVE_WRITES_NEEDS_LETTER"}
    assert review.profile_text is None
    assert review.warnings == ()


@pytest.mark.parametrize("value", ["sim", "true", 1, "yes", ["x"], {"a": 1}])
def test_a_value_that_is_not_a_boolean_is_refused_and_never_turns_writes_on(value: object) -> None:
    review = _review(_letter(answer(value, "carta", QUOTE)))

    assert _codes(review) == {FIELD: "INVALID_VALUE"}
    assert review.profile_text is None


def test_a_malformed_answer_shape_is_refused_by_the_letter_model() -> None:
    data = _letter({"value": True})

    with pytest.raises(ConfigError, match="allow_invalid_input_writes"):
        Letter.from_data(data)
