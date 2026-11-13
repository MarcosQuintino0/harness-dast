"""Testes independentes (QA) de padrões de caminho, com oráculo escrito à parte."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.pathpattern import covers, matches, parse_pattern

_ALPHABET = ["a", "b", "c", "A"]
_segment = st.sampled_from(_ALPHABET)
_pattern_token = st.sampled_from([*_ALPHABET, "*", "**"])
_patterns = st.lists(_pattern_token, max_size=5).map(tuple)
_paths = st.lists(_segment, max_size=6).map(tuple)


def oracle_matches(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    """Oráculo por expressão regular sobre o caminho unido por '/'."""
    regex = ""
    for token in pattern:
        if token == "**":
            regex += "(?:/[^/]+)*"
        elif token == "*":
            regex += "/[^/]+"
        else:
            regex += "/" + re.escape(token)
    full = "".join("/" + segment for segment in path)
    return re.fullmatch(regex or "", full) is not None if (regex or full) else True


@settings(max_examples=500, deadline=None)
@given(pattern=_patterns, path=_paths)
def test_matches_agrees_with_regex_oracle_when_inputs_are_random(
    pattern: tuple[str, ...], path: tuple[str, ...]
) -> None:
    assert matches(pattern, path) is oracle_matches(pattern, path)


@settings(max_examples=500, deadline=None)
@given(wide=_patterns, narrow=_patterns, path=_paths)
def test_covers_is_sound_when_checked_against_matches(
    wide: tuple[str, ...], narrow: tuple[str, ...], path: tuple[str, ...]
) -> None:
    # covers() pode ser conservador (False), mas True nunca pode mentir.
    if covers(wide, narrow) and matches(narrow, path):
        assert matches(wide, path)


@settings(max_examples=300, deadline=None)
@given(pattern=_patterns)
def test_covers_is_reflexive_when_pattern_is_valid(pattern: tuple[str, ...]) -> None:
    assert covers(pattern, pattern)


@settings(max_examples=300, deadline=None)
@given(pattern=_patterns, path=_paths)
def test_matches_with_fold_is_superset_of_exact_match(
    pattern: tuple[str, ...], path: tuple[str, ...]
) -> None:
    if matches(pattern, path):
        assert matches(pattern, path, fold=True)


def test_matches_fold_ignores_case_and_unicode_composition() -> None:
    assert matches(("café",), ("café",), fold=True)
    assert matches(("admin",), ("ADMIN",), fold=True)
    assert not matches(("admin",), ("ADMIN",))
    assert matches(("admin",), ("ａdmin",), fold=True)  # 'a' de largura total (NFKC)


def test_matches_is_linear_enough_when_pattern_has_many_double_stars() -> None:
    pattern = ("**",) * 40 + ("x",)
    path = ("a",) * 200

    assert not matches(pattern, path)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "api",
        "api/x",
        "//api",
        "/api//x",
        "/api/./x",
        "/api/../x",
        "/api/us*",
        "/api/*.json",
        "/api/***",
        "/api/**x",
        "/api/%2e",
        "/api/a;b",
        "/api/a?b",
        "/api/a#b",
        "/api/a\\b",
        "/api/a b",
        "/api/a\tb",
        "/api/a\nb",
        "/api/a​b",
        "/api/a‮b",
        "/api/\x00",
        "/" + "a" * 300,
        " /api",
        "/api ",
    ],
)
def test_parse_pattern_rejects_when_pattern_is_ambiguous_or_dangerous(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_pattern(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("/", ()), ("/api", ("api",)), ("/api/", ("api",)), ("/a/*/**", ("a", "*", "**"))],
)
def test_parse_pattern_returns_segments_when_pattern_is_valid(
    raw: str, expected: tuple[str, ...]
) -> None:
    assert parse_pattern(raw) == expected


def test_parse_pattern_error_does_not_repeat_the_whole_pattern() -> None:
    secret = "SEGREDO-NO-PADRAO-123"

    with pytest.raises(ValueError) as caught:
        parse_pattern(f"/{secret}/a b")

    assert secret not in str(caught.value)
