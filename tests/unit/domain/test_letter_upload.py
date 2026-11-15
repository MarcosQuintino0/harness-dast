"""Carta: `attack.allow_upload_scan` vira `scan.allow_upload_scan` só com a carta (ADR 0052)."""

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
QUOTE = "Autorizamos o ZAP a varrer o envio de arquivos no ambiente de teste."
FIELD = "attack.allow_upload_scan"


def _review(data: dict[str, Any]) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", TODAY)


def _letter(upload: dict[str, Any] | None, **attack: Any) -> dict[str, Any]:
    data = valid_letter_data()
    data["attack"] = dict(attack)
    if upload is not None:
        data["attack"]["allow_upload_scan"] = upload
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
    assert "allow_upload_scan" not in plain.profile_text
    assert "scan.allow_upload_scan" not in plain.blocks
    assert _profile(plain).scan.allow_upload_scan is False
    assert "UPLOAD_SCAN_AUTHORIZED" not in [w.code for w in plain.warnings]


@pytest.mark.parametrize(
    "upload",
    [
        {"source": "desconhecido"},
        {"value": None, "source": "pessoa"},
        {"value": False, "source": "carta", "quote": QUOTE},
        {"value": False, "source": "pessoa"},
    ],
)
def test_unknown_null_or_false_keeps_the_upload_scan_off_without_any_pending_item(
    upload: dict[str, Any],
) -> None:
    review = _review(_letter(upload))

    assert review.ready
    assert review.profile_text is not None
    assert "allow_upload_scan" not in review.profile_text
    assert _profile(review).scan.allow_upload_scan is False
    assert "UPLOAD_SCAN_AUTHORIZED" not in [w.code for w in review.warnings]


def test_true_from_the_letter_with_a_quote_generates_the_key_and_warns_to_confirm() -> None:
    review = _review(_letter(answer(True, "carta", QUOTE)))

    assert review.ready
    assert "scan.allow_upload_scan" in review.blocks
    assert _profile(review).scan.allow_upload_scan is True
    assert review.profile_text is not None
    assert "allow_upload_scan: true" in review.profile_text
    assert "(ADR 0052): scan.allow_upload_scan" in review.profile_text
    warning = next(w for w in review.warnings if w.code == "UPLOAD_SCAN_AUTHORIZED")
    assert warning.field == FIELD
    assert "Confirme com o dono do produto" in warning.message


def test_the_upload_key_sits_beside_the_other_scan_keys_of_the_letter() -> None:
    review = _review(
        _letter(
            answer(True, "carta", QUOTE),
            strength=answer("MEDIUM", "pessoa"),
            include_outcomes=answer(["not_found"], "carta"),
        )
    )

    profile = _profile(review)
    assert profile.scan.strength == "MEDIUM"
    assert profile.scan.include_outcomes == ("not_found",)
    assert profile.scan.allow_upload_scan is True


def test_the_generated_text_is_deterministic() -> None:
    data = _letter(answer(True, "carta", QUOTE))

    assert _review(data).profile_text == _review(data).profile_text


@pytest.mark.parametrize(
    "upload",
    [answer(True, "pessoa", QUOTE), answer(True, "carta"), answer(True, "carta", "   ")],
)
def test_true_without_the_letter_as_source_or_without_a_quote_is_refused(
    upload: dict[str, Any],
) -> None:
    review = _review(_letter(upload))

    assert _codes(review) == {FIELD: "UPLOAD_SCAN_NEEDS_LETTER"}
    assert review.profile_text is None
    assert review.warnings == ()


@pytest.mark.parametrize("value", ["sim", "true", 1, "yes", ["x"], {"a": 1}])
def test_a_value_that_is_not_a_boolean_is_refused_and_never_turns_the_scan_on(
    value: object,
) -> None:
    review = _review(_letter(answer(value, "carta", QUOTE)))

    assert _codes(review) == {FIELD: "INVALID_VALUE"}
    assert review.profile_text is None


def test_a_malformed_answer_shape_is_refused_by_the_letter_model() -> None:
    data = _letter({"value": True})

    with pytest.raises(ConfigError, match="allow_upload_scan"):
        Letter.from_data(data)
