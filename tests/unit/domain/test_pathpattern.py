import pytest

from harness_dast.domain.pathpattern import (
    covers,
    fold_segment,
    format_pattern,
    matches,
    parse_pattern,
)


def segments(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split("/") if part)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        pytest.param("/api/**", "/api", True, id="double_star_matches_zero_segments"),
        pytest.param("/api/**", "/api/a", True, id="double_star_matches_one_segment"),
        pytest.param("/api/**", "/api/a/b/c", True, id="double_star_matches_deep_path"),
        pytest.param("/api/**", "/apix", False, id="double_star_does_not_match_sibling_prefix"),
        pytest.param("/api/**", "/", False, id="double_star_does_not_match_root_above_prefix"),
        pytest.param("/api/*", "/api/a", True, id="star_matches_exactly_one_segment"),
        pytest.param("/api/*", "/api", False, id="star_does_not_match_zero_segments"),
        pytest.param("/api/*", "/api/a/b", False, id="star_does_not_match_two_segments"),
        pytest.param("/api/*/items", "/api/7/items", True, id="star_in_the_middle"),
        pytest.param("/api/*/items", "/api/7/8/items", False, id="star_in_the_middle_is_one_only"),
        pytest.param("/api/**/items", "/api/items", True, id="double_star_in_middle_zero"),
        pytest.param("/api/**/items", "/api/a/b/items", True, id="double_star_in_middle_many"),
        pytest.param("/api/**/items", "/api/a/b/other", False, id="double_star_needs_suffix"),
        pytest.param("/", "/", True, id="root_matches_root"),
        pytest.param("/", "/a", False, id="root_does_not_match_child"),
        pytest.param("/api/x", "/api/x", True, id="literal_exact"),
        pytest.param("/api/x", "/api/X", False, id="literal_is_case_sensitive"),
        pytest.param("/api/x", "/api/x/y", False, id="literal_is_not_a_prefix"),
        pytest.param("/api/x/", "/api/x", True, id="trailing_slash_in_pattern_is_ignored"),
        pytest.param("/**", "/", True, id="catch_all_matches_root"),
        pytest.param("/**", "/a/b", True, id="catch_all_matches_anything"),
        pytest.param("/**/**", "/a", True, id="consecutive_double_stars"),
    ],
)
def test_matches_follows_documented_semantics_when_pattern_is_given(
    pattern: str, path: str, expected: bool
) -> None:
    result = matches(parse_pattern(pattern), segments(path))

    assert result is expected


def test_matches_ignores_case_when_fold_is_enabled() -> None:
    result = matches(parse_pattern("/api/conta/excluir"), segments("/API/Conta/EXCLUIR"), fold=True)

    assert result is True


def test_matches_is_case_sensitive_when_fold_is_disabled() -> None:
    result = matches(parse_pattern("/api/conta"), segments("/API/conta"))

    assert result is False


def test_fold_segment_unifies_compatibility_forms_when_unicode_is_composed_differently() -> None:
    assert fold_segment("\uff21\uff24\uff2d\uff29\uff2e") == fold_segment("admin")


def test_matches_does_not_blow_up_when_pattern_has_many_double_stars() -> None:
    pattern = parse_pattern("/" + "/".join(["**"] * 30) + "/x")

    result = matches(pattern, tuple("a" * 1 for _ in range(60)))

    assert result is False


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("api/x", id="no_leading_slash"),
        pytest.param("/api//x", id="empty_segment"),
        pytest.param("/api/./x", id="dot_segment"),
        pytest.param("/api/../x", id="dotdot_segment"),
        pytest.param("/api/us*", id="partial_wildcard_suffix"),
        pytest.param("/api/*.json", id="partial_wildcard_prefix"),
        pytest.param("/api/***", id="triple_star"),
        pytest.param("/api/a b", id="space"),
        pytest.param("/api/a\tb", id="tab"),
        pytest.param("/api/a\u00a0b", id="non_breaking_space"),
        pytest.param("/api/a\x00b", id="nul"),
        pytest.param("/api/a\\b", id="backslash"),
        pytest.param("/api/%2e%2e", id="percent_sign"),
        pytest.param("/api/a;b", id="semicolon"),
        pytest.param("/api/a?b", id="question_mark"),
        pytest.param("/api/a#b", id="hash"),
        pytest.param("/api/a\u200bb", id="zero_width_space"),
        pytest.param("/" + "a" * 300, id="too_long"),
    ],
)
def test_parse_pattern_rejects_when_pattern_is_dangerous_or_ambiguous(raw: str) -> None:
    with pytest.raises(ValueError, match=r"padrão|curinga"):
        parse_pattern(raw)


def test_parse_pattern_returns_segments_when_pattern_is_valid() -> None:
    assert parse_pattern("/api/*/x/**") == ("api", "*", "x", "**")


def test_parse_pattern_returns_empty_tuple_when_pattern_is_root() -> None:
    assert parse_pattern("/") == ()


def test_format_pattern_roundtrips_when_pattern_is_canonical() -> None:
    assert format_pattern(parse_pattern("/api/x/")) == "/api/x"


@pytest.mark.parametrize(
    ("wide", "narrow", "expected"),
    [
        pytest.param("/api/**", "/api/users/*", True, id="double_star_covers_star_child"),
        pytest.param("/api/**", "/api/**", True, id="same_pattern"),
        pytest.param("/api/**", "/api", True, id="double_star_covers_its_own_base"),
        pytest.param("/api/*", "/api/**", False, id="star_does_not_cover_double_star"),
        pytest.param("/api/users", "/api/*", False, id="literal_does_not_cover_star"),
        pytest.param("/api/*", "/api/users", True, id="star_covers_literal"),
        pytest.param("/api/users/**", "/api/orders", False, id="different_branch"),
        pytest.param("/api", "/api/users", False, id="shorter_does_not_cover_longer"),
        pytest.param("/api/**/x", "/api/*/x", True, id="inner_double_star_covers_star"),
        pytest.param("/api/**", "/other", False, id="outside_prefix"),
        pytest.param("/api/x", "/api/X", False, id="case_sensitive"),
    ],
)
def test_covers_is_sound_when_comparing_patterns(wide: str, narrow: str, expected: bool) -> None:
    result = covers(parse_pattern(wide), parse_pattern(narrow))

    assert result is expected


def test_covers_finishes_quickly_when_search_space_is_large_and_pattern_does_not_fit() -> None:
    wide = parse_pattern("/" + "/".join(["**"] * 12) + "/x")
    narrow = parse_pattern("/a/b/c/d/e/f/y")

    assert covers(wide, narrow) is False
