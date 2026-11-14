"""Formatos do painel: números, datas, durações e palavras de estado (system/formats.html)."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain.panel_format import (
    CONFIDENCE_WORDS,
    FUNCTION_STATE_WORDS,
    NO_DATA,
    NOT_MEASURED,
    RUN_STATE_WORDS,
    STAGE_WORDS,
    capitalize_first,
    count_word,
    fmt_clock,
    fmt_count,
    fmt_date,
    fmt_datetime,
    fmt_duration,
    fmt_tokens,
    plural,
    product_title,
    x_of_y,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (26, "26"),
        (999, "999"),
        (1000, "1.000"),
        (16854, "16.854"),
        (1234567, "1.234.567"),
    ],
)
def test_fmt_count_uses_dot_as_thousands_separator(value: int, expected: str) -> None:
    assert fmt_count(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (812, "812"),
        (999, "999"),
        (1000, "1 mil"),
        (151_000, "151 mil"),
        (151_400, "151 mil"),
        (151_600, "152 mil"),
        (999_999, "1,0 mi"),
        (1_200_000, "1,2 mi"),
    ],
)
def test_fmt_tokens_follows_the_design_scale(value: int, expected: str) -> None:
    assert fmt_tokens(value) == expected


def test_fmt_tokens_without_data_is_a_dash_and_the_words_not_zero() -> None:
    assert fmt_tokens(None) == NOT_MEASURED
    assert NOT_MEASURED.startswith(NO_DATA)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 s"),
        (20, "20 s"),
        (59.4, "59 s"),
        (60, "1 min"),
        (28 * 60, "28 min"),
        (59 * 60, "59 min"),
        (3600, "1 h 00"),
        (97 * 60, "1 h 37"),
        (3 * 3600 + 5 * 60, "3 h 05"),
        (-5, "0 s"),
    ],
)
def test_fmt_duration_uses_seconds_minutes_then_hours(seconds: float, expected: str) -> None:
    assert fmt_duration(seconds) == expected


def test_fmt_duration_without_data_is_not_measured() -> None:
    assert fmt_duration(None) == NOT_MEASURED


def test_dates_use_day_month_year_and_the_dot_between_date_and_time() -> None:
    moment = datetime(2026, 11, 13, 20, 8, 5, tzinfo=UTC)

    assert fmt_datetime(moment) == "13/11/2026 · 20:08"
    assert fmt_date(moment) == "13/11/2026"
    assert fmt_clock(moment) == "20:08:05"


def test_dates_without_data_are_a_dash() -> None:
    assert fmt_datetime(None) == fmt_date(None) == fmt_clock(None) == NO_DATA


def test_x_of_y_is_never_a_percentage() -> None:
    assert x_of_y(26, 30) == "26 de 30"
    assert x_of_y(8203, 16854) == "8.203 de 16.854"


@pytest.mark.parametrize(
    ("value", "expected"), [(1, "uma"), (2, "duas"), (3, "três"), (8, "oito"), (9, "9"), (12, "12")]
)
def test_count_word_spells_small_feminine_numbers(value: int, expected: str) -> None:
    assert count_word(value) == expected


def test_plural_uses_singular_only_for_one() -> None:
    assert plural(1, "falha", "falhas") == "1 falha"
    assert plural(0, "falha", "falhas") == "0 falhas"
    assert plural(1500, "pedido", "pedidos") == "1.500 pedidos"


def test_capitalize_first_keeps_the_rest_untouched() -> None:
    assert capitalize_first("duas falhas e uma API") == "Duas falhas e uma API"
    assert capitalize_first("") == ""


def test_product_title_turns_the_slug_into_a_name() -> None:
    assert product_title("clinica-piloto") == "Clinica Piloto"
    assert product_title("agenda") == "Agenda"


def test_state_words_are_the_closed_list_of_the_design() -> None:
    assert set(RUN_STATE_WORDS.values()) == {"ao vivo", "terminou", "parou no meio", "erro"}
    assert set(FUNCTION_STATE_WORDS.values()) == {
        "atacada",
        "com falha grave",
        "não testada",
        "proibida pela carta",
    }
    assert CONFIDENCE_WORDS == ("a confirmar", "prova forte", "confirmada")
    assert set(STAGE_WORDS.values()) == {"feita", "parou no meio", "não rodou"}


def test_no_state_word_promises_safety() -> None:
    every = [
        *RUN_STATE_WORDS.values(),
        *FUNCTION_STATE_WORDS.values(),
        *CONFIDENCE_WORDS,
        *STAGE_WORDS.values(),
    ]
    assert not any("segur" in word or "aprov" in word for word in every)
