"""Política do `probe`: balde de fichas e `Retry-After`."""

import pytest

from harness_dast.domain.probe_policy import (
    DEFAULT_RETRY_AFTER_SECONDS,
    MAX_RETRY_AFTER_SECONDS,
    TokenBucket,
    parse_retry_after,
)


def test_first_reservation_is_immediate_and_later_ones_respect_the_interval() -> None:
    bucket = TokenBucket(4.0)

    assert bucket.reserve(100.0) == 0.0
    assert bucket.reserve(100.0) == pytest.approx(0.25)
    assert bucket.reserve(100.0) == pytest.approx(0.5)


def test_waiting_in_real_time_pays_the_debt() -> None:
    bucket = TokenBucket(2.0)
    bucket.reserve(0.0)

    assert bucket.reserve(0.5) == 0.0
    assert bucket.reserve(0.6) == pytest.approx(0.4)


def test_a_long_pause_does_not_allow_a_burst() -> None:
    bucket = TokenBucket(1.0)
    bucket.reserve(0.0)

    assert bucket.reserve(1000.0) == 0.0
    assert bucket.reserve(1000.0) == pytest.approx(1.0)


@pytest.mark.parametrize("rate", [0, -1, -0.5])
def test_the_rate_must_be_positive(rate: float) -> None:
    with pytest.raises(ValueError, match="maior que zero"):
        TokenBucket(rate)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", 3.0),
        (" 7 ", 7.0),
        ("0", 0.0),
        ("9999", MAX_RETRY_AFTER_SECONDS),
        (None, DEFAULT_RETRY_AFTER_SECONDS),
        ("", DEFAULT_RETRY_AFTER_SECONDS),
        ("-5", DEFAULT_RETRY_AFTER_SECONDS),
        ("Wed, 21 Oct 2026 07:28:00 GMT", DEFAULT_RETRY_AFTER_SECONDS),
        ("1.5", DEFAULT_RETRY_AFTER_SECONDS),
        ("²", DEFAULT_RETRY_AFTER_SECONDS),
    ],
)
def test_retry_after_is_bounded_and_garbage_gets_the_default(
    value: str | None, expected: float
) -> None:
    assert parse_retry_after(value) == expected
