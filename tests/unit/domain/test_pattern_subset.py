import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.pattern_subset import matches, parse_pattern, synthesize

SUPPORTED = [
    "^[A-Z]{3}[0-9]{2}$",
    r"^\d{4}$",
    "^[a-z]+$",
    r"^\w{2,5}-\d?$",
    r"^[^0-9]{3}$",
    "^a.c$",
    r"^\.\-x$",
    "[0-9]{3}",
    "^[a-c-]{2}$",
    r"^\D\S\W$",
    "^ab*c+d?$",
    "^[abc]{2,}$",
]
UNSUPPORTED = [
    "(a|b)",
    "^(ab)+$",
    "a|b",
    r"\bword",
    "a{",
    "a{x}",
    "a{3,1}",
    "a{999}",
    "a{1,x}",
    "[a-",
    "[z-a]",
    "[[]",
    "^a^b$",
    "a$b",
    r"\p{L}",
    "*a",
    "a??",
    "{2}",
    "[a-z",
    r"[\D]",
    "a\\",
    "[\\",
    "[a-\\",
    "[\u0000-￿]",
    "x" * 201,
]


@pytest.mark.parametrize("pattern", SUPPORTED)
def test_parse_pattern_accepts_when_pattern_is_in_the_safe_subset(pattern: str) -> None:
    assert parse_pattern(pattern) is not None


@pytest.mark.parametrize("pattern", UNSUPPORTED)
def test_parse_pattern_returns_none_when_pattern_leaves_the_safe_subset(pattern: str) -> None:
    assert parse_pattern(pattern) is None


@pytest.mark.parametrize("pattern", SUPPORTED)
def test_synthesize_matches_python_re_when_pattern_is_supported(pattern: str) -> None:
    parsed = parse_pattern(pattern)
    assert parsed is not None

    text = synthesize(parsed, 0, None)

    assert text is not None
    assert re.search(pattern, text) is not None
    assert matches(parsed, text)


def test_synthesize_extends_to_reach_min_length() -> None:
    parsed = parse_pattern("^[a-z]+$")
    assert parsed is not None

    text = synthesize(parsed, 7, None)

    assert text is not None
    assert len(text) == 7


def test_synthesize_returns_none_when_max_length_is_too_small() -> None:
    parsed = parse_pattern("^[a-z]{5}$")
    assert parsed is not None

    assert synthesize(parsed, 0, 3) is None


def test_synthesize_returns_none_when_min_length_cannot_be_reached() -> None:
    parsed = parse_pattern("^[a-z]{2}$")
    assert parsed is not None

    assert synthesize(parsed, 9, None) is None


def test_matches_requires_full_match_when_pattern_is_anchored() -> None:
    parsed = parse_pattern("^[a-z]{3}$")
    assert parsed is not None

    assert matches(parsed, "abc")
    assert not matches(parsed, "abcd")
    assert not matches(parsed, "xabc")


def test_matches_means_contains_when_pattern_is_not_anchored() -> None:
    parsed = parse_pattern("[0-9]{3}")
    assert parsed is not None

    assert matches(parsed, "ab123cd")
    assert not matches(parsed, "ab12cd")


def test_matches_is_false_when_text_is_longer_than_the_limit() -> None:
    parsed = parse_pattern("^a*$")
    assert parsed is not None

    assert not matches(parsed, "a" * 3000)


def test_matches_stays_fast_when_pattern_would_explode_in_a_backtracking_engine() -> None:
    parsed = parse_pattern("^a*a*a*a*a*a*a*a*b$")
    assert parsed is not None

    assert not matches(parsed, "a" * 1500)


@given(st.text(alphabet="abc012-", max_size=12))
def test_matches_agrees_with_python_re_on_a_safe_pattern(text: str) -> None:
    pattern = "^[ab]{1,3}[0-2]*-?$"
    parsed = parse_pattern(pattern)
    assert parsed is not None

    assert matches(parsed, text) == (re.fullmatch(pattern, text) is not None)


@given(st.text(alphabet="abc012-", max_size=12))
def test_matches_agrees_with_python_re_search_when_unanchored(text: str) -> None:
    pattern = "[bc]{2}0"
    parsed = parse_pattern(pattern)
    assert parsed is not None

    assert matches(parsed, text) == (re.search(pattern, text) is not None)


def test_synthesize_uses_members_when_class_has_only_special_characters() -> None:
    parsed = parse_pattern(r"^[\.\-]{2}$")
    assert parsed is not None

    text = synthesize(parsed, 0, None)

    assert text is not None
    assert set(text) <= {".", "-"}


def test_synthesize_finds_a_printable_char_when_class_negates_every_letter_and_digit() -> None:
    parsed = parse_pattern(r"^[^a-zA-Z0-9]$")
    assert parsed is not None

    text = synthesize(parsed, 0, None)

    assert text is not None
    assert not text.isalnum()


def test_synthesize_falls_back_to_a_member_when_the_class_has_only_non_ascii_characters() -> None:
    parsed = parse_pattern("^[é]$")
    assert parsed is not None

    assert synthesize(parsed, 0, None) == "é"


def test_parse_pattern_rejects_a_class_that_grows_past_the_limit_with_several_ranges() -> None:
    assert parse_pattern("[a-ÿĀ-ǿ]") is None
