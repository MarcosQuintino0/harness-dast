import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.unique_values import (
    MAX_UNIQUE_TOKENS,
    counter_digits,
    run_tag_from_run_id,
    unique_digits,
    unique_token,
    validate_run_tag,
)


def test_validate_run_tag_accepts_hex_between_four_and_eight_digits() -> None:
    assert validate_run_tag("7f3a") == "7f3a"
    assert validate_run_tag("7f3a9c01") == "7f3a9c01"


@pytest.mark.parametrize("tag", ["", "abc", "7F3A", "7f3g", "7f3a9c012", "../x1"])
def test_validate_run_tag_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ConfigError):
        validate_run_tag(tag)


def test_run_tag_from_run_id_takes_the_suffix() -> None:
    assert run_tag_from_run_id("2026-11-12T21-04-11Z-agenda-7f3a") == "7f3a"


def test_run_tag_from_run_id_rejects_a_value_without_hex_suffix() -> None:
    with pytest.raises(ConfigError):
        run_tag_from_run_id("agenda")


def test_unique_token_joins_tag_and_four_hex_counter() -> None:
    assert unique_token("7f3a", 18) == "7f3a0012"


def test_unique_token_truncates_the_tag_but_never_the_counter_when_field_is_short() -> None:
    assert unique_token("7f3a9c01", 255, max_length=6) == "7f" + "00ff"


def test_unique_token_rejects_a_field_shorter_than_the_counter() -> None:
    with pytest.raises(ConfigError, match="menor que"):
        unique_token("7f3a", 1, max_length=3)


@pytest.mark.parametrize("counter", [-1, MAX_UNIQUE_TOKENS])
def test_unique_token_rejects_counter_outside_capacity(counter: int) -> None:
    with pytest.raises(ConfigError, match="mais de"):
        unique_token("7f3a", counter)


def test_counter_digits_follows_the_documented_scheme() -> None:
    assert [counter_digits(w) for w in (1, 4, 5, 8, 9, 12, 14)] == [1, 4, 4, 4, 4, 6, 7]


def test_unique_digits_puts_tag_prefix_then_zero_padded_counter() -> None:
    value = unique_digits("7f3a", 12, 9)

    assert value == str(0x7F3A % 10**5).zfill(5) + "0012"


def test_unique_digits_uses_only_the_counter_when_width_is_small() -> None:
    assert unique_digits("7f3a", 7, 3) == "007"


@pytest.mark.parametrize("counter", [-1, 10_000])
def test_unique_digits_rejects_counter_outside_capacity_of_nine_digits(counter: int) -> None:
    with pytest.raises(ConfigError, match="mais de"):
        unique_digits("7f3a", counter, 9)


@given(st.integers(min_value=1, max_value=30), st.integers(min_value=0, max_value=9999))
def test_unique_digits_has_exact_width_and_only_digits(width: int, counter: int) -> None:
    if counter >= 10 ** counter_digits(width):
        return

    value = unique_digits("a1b2", counter, width)

    assert len(value) == width
    assert value.isdigit()


@given(st.sets(st.integers(min_value=0, max_value=9999), min_size=2, max_size=50))
def test_unique_digits_never_repeats_for_distinct_counters(counters: set[int]) -> None:
    values = {unique_digits("a1b2", counter, 9) for counter in counters}

    assert len(values) == len(counters)
