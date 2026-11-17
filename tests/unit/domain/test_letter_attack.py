"""Carta: chaves `attack.*` da V1.12 viram `scan.*` e `extra_checks` só com a carta (ADR 0096)."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

TODAY = date(2026, 11, 17)
QUOTE = "Autorizamos esta capacidade no ambiente de teste."
FLAGS = ("inject_headers", "oast", "allow_rate_tests", "experimental_rules", "inventory")


def _review(**attack: Any) -> LetterReview:
    data = valid_letter_data()
    data["attack"] = dict(attack)
    return review_letter(Letter.from_data(data), "demo", TODAY)


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def test_a_letter_without_the_keys_generates_the_same_profile_as_before() -> None:
    plain = review_letter(Letter.from_data(valid_letter_data()), "demo", TODAY)
    empty = _review()

    assert plain.ready
    assert plain.profile_text == empty.profile_text
    assert plain.profile_text is not None
    for name in ("pacing", "inject_headers", "oast", "extra_checks", "allow_rate_tests"):
        assert name not in plain.profile_text
    profile = _profile(plain)
    assert profile.scan.pacing == "legacy"
    assert profile.extra_checks.is_default()
    assert "ATTACK_FLAG_AUTHORIZED" not in [w.code for w in plain.warnings]


@pytest.mark.parametrize("name", ["pacing", *FLAGS])
@pytest.mark.parametrize(
    "response",
    [
        {"source": "desconhecido"},
        {"value": None, "source": "pessoa"},
    ],
)
def test_unknown_or_null_answers_keep_every_key_off_without_pending_items(
    name: str, response: dict[str, Any]
) -> None:
    review = _review(**{name: response})

    assert review.ready
    assert _profile(review).extra_checks.is_default()
    assert _profile(review).scan.pacing == "legacy"


@pytest.mark.parametrize("name", FLAGS)
def test_false_keeps_the_flag_off(name: str) -> None:
    review = _review(**{name: answer(False, "carta", QUOTE)})

    assert review.ready
    assert review.profile_text is not None
    assert name not in review.profile_text


@pytest.mark.parametrize("name", FLAGS)
def test_true_from_the_letter_with_a_quote_generates_the_key_and_warns(name: str) -> None:
    review = _review(**{name: answer(True, "carta", QUOTE)})

    assert review.ready
    assert review.profile_text is not None
    assert f"{name}: true" in review.profile_text
    assert "(ADR 0096)" in review.profile_text
    warning = next(w for w in review.warnings if w.code == "ATTACK_FLAG_AUTHORIZED")
    assert warning.field == f"attack.{name}"
    assert "Confirme com o dono do produto" in warning.message


def test_the_flags_land_in_their_profile_blocks() -> None:
    review = _review(**{name: answer(True, "carta", QUOTE) for name in FLAGS})
    profile = _profile(review)

    assert profile.scan.inject_headers is True
    assert profile.scan.oast is True
    assert profile.extra_checks.allow_rate_tests is True
    assert profile.extra_checks.experimental_rules is True
    assert profile.extra_checks.inventory is True
    assert {"scan.inject_headers", "scan.oast", "extra_checks"} <= set(review.blocks)


@pytest.mark.parametrize("name", FLAGS)
@pytest.mark.parametrize(
    "response",
    [answer(True, "pessoa", QUOTE), answer(True, "carta"), answer(True, "carta", "  ")],
)
def test_true_without_the_letter_or_the_quote_is_a_pending_item(
    name: str, response: dict[str, Any]
) -> None:
    review = _review(**{name: response})

    assert not review.ready
    assert {i.field: i.code for i in review.issues} == {
        f"attack.{name}": "ATTACK_FLAG_NEEDS_LETTER"
    }


@pytest.mark.parametrize("name", FLAGS)
@pytest.mark.parametrize("value", ["sim", 1, ["true"]])
def test_a_flag_with_a_non_boolean_value_is_invalid(name: str, value: object) -> None:
    review = _review(**{name: answer(value, "carta", QUOTE)})

    assert not review.ready
    assert {i.field: i.code for i in review.issues} == {f"attack.{name}": "INVALID_VALUE"}


@pytest.mark.parametrize("source", ["carta", "pessoa"])
def test_pacing_proxy_from_the_letter_or_the_person_generates_scan_pacing(source: str) -> None:
    review = _review(pacing=answer("proxy", source))

    assert review.ready
    assert _profile(review).scan.pacing == "proxy"
    assert "scan.pacing" in review.blocks
    assert review.profile_text is not None
    assert 'pacing: "proxy"' in review.profile_text


def test_pacing_legacy_is_the_default_and_generates_nothing() -> None:
    review = _review(pacing=answer("legacy", "carta"))

    assert review.ready
    assert review.profile_text is not None
    assert "pacing" not in review.profile_text
    assert "scan.pacing" not in review.blocks


@pytest.mark.parametrize("value", ["fast", "PROXY", True, 3, ["proxy"]])
def test_pacing_with_an_invalid_value_is_a_pending_item(value: object) -> None:
    review = _review(pacing=answer(value))

    assert not review.ready
    assert {i.field: i.code for i in review.issues} == {"attack.pacing": "INVALID_VALUE"}


def test_an_unknown_key_in_the_attack_section_is_rejected() -> None:
    data = valid_letter_data()
    data["attack"] = {"oast_everywhere": answer(True)}

    with pytest.raises(ConfigError):
        Letter.from_data(data)


def test_an_answer_with_the_wrong_shape_is_rejected() -> None:
    data = valid_letter_data()
    data["attack"] = {"oast": True}

    with pytest.raises(ConfigError):
        Letter.from_data(data)
