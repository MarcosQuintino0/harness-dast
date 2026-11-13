"""Analisador léxico do SQL de limpeza."""

import pytest

from harness_dast.domain.cleanup_sql import LexError, TokenKind, tokenize


def kinds(text: str) -> list[tuple[str, str]]:
    return [(token.kind.value, token.text) for token in tokenize(text)]


def test_splits_words_binds_numbers_strings_operators_and_semicolons() -> None:
    result = kinds("DELETE FROM t.x WHERE a >= :run_start AND b = 'o''k' || 1.5e3;")

    assert result == [
        ("word", "DELETE"),
        ("word", "FROM"),
        ("word", "t"),
        ("op", "."),
        ("word", "x"),
        ("word", "WHERE"),
        ("word", "a"),
        ("op", ">="),
        ("bind", ":run_start"),
        ("word", "AND"),
        ("word", "b"),
        ("op", "="),
        ("string", "'o''k'"),
        ("op", "||"),
        ("number", "1.5e3"),
        ("semi", ";"),
    ]


def test_drops_whitespace_and_both_kinds_of_comment() -> None:
    assert kinds("a -- x\n b /* y\n z */ c") == [("word", "a"), ("word", "b"), ("word", "c")]


def test_tracks_the_line_of_each_token_across_comments_and_strings() -> None:
    tokens = tokenize("a\n/* x\ny */ b\n'l1\nl2' c")

    assert [(t.text, t.line) for t in tokens] == [("a", 1), ("b", 3), ("'l1\nl2'", 4), ("c", 5)]


def test_token_helpers_ignore_case_for_words() -> None:
    token = tokenize("delete")[0]

    assert token.kind is TokenKind.WORD
    assert token.upper == "DELETE"
    assert token.is_word("DELETE")
    assert not token.is_op("(")


def test_q_literal_keeps_quotes_and_semicolons_inside() -> None:
    assert kinds("q'[a'b;c]' ;") == [("string", "q'[a'b;c]'"), ("semi", ";")]


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("a @ b", "@"),
        ("a & b", "&"),
        ("'&x'", "&"),
        ('a "b" c', "aspas duplas"),
        ("a : b", "':'"),
        ("a := 1", "':'"),
        ("'aberto", "sem fechamento"),
        ("/* aberto", "sem fechamento"),
        ("q'[aberto", "sem fechamento"),
        ("q' x'", "delimitador"),
        ("a \x00 b", "controle"),
        ("a\rb", "Retorno de carro"),
        ("a ç b", "ASCII"),
        ("a ? b", "inesperado"),
        ("a | b", "inesperado"),
    ],
)
def test_rejects_what_it_cannot_read_with_certainty(text: str, fragment: str) -> None:
    with pytest.raises(LexError) as caught:
        tokenize(text)

    assert fragment in caught.value.message


def test_reports_the_line_of_the_offending_character() -> None:
    with pytest.raises(LexError) as caught:
        tokenize("a\nb\n@")

    assert "linha 3" in caught.value.message


def test_accepts_crlf_line_endings() -> None:
    assert kinds("a\r\n-- c\r\nb") == [("word", "a"), ("word", "b")]
