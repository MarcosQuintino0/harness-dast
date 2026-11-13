"""Testes independentes (QA) de RunId e RunLimits."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import RunId, RunLimits


def test_create_formats_utc_stamp_when_started_at_has_other_offset() -> None:
    started = datetime(2026, 11, 12, 22, 4, 11, tzinfo=timezone(timedelta(hours=-3)))

    run_id = RunId.create(started_at=started, product="agenda", suffix="7f3a")

    assert str(run_id) == "2026-11-13T01-04-11Z-agenda-7f3a"


def test_create_raises_config_error_when_started_at_is_naive() -> None:
    with pytest.raises(ConfigError):
        RunId.create(started_at=datetime(2026, 1, 1), product="agenda", suffix="7f3a")


@pytest.mark.parametrize(
    "product", ["", "A", "a b", "a/b", "../x", "a.b", "-a", "a-", "x" * 41, "á"]
)
def test_create_raises_when_product_is_not_a_slug(product: str) -> None:
    with pytest.raises(ValueError):
        RunId.create(started_at=datetime(2026, 1, 1, tzinfo=UTC), product=product, suffix="7f3a")


@pytest.mark.parametrize(
    "suffix", ["", "abc", "ABCD", "7f3g", "7f3a7f3a7", "7f3a/", "../..", "7f 3a"]
)
def test_create_raises_when_suffix_is_not_4_to_8_lowercase_hex(suffix: str) -> None:
    with pytest.raises(ValueError):
        RunId.create(started_at=datetime(2026, 1, 1, tzinfo=UTC), product="agenda", suffix=suffix)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "../x",
        "2026-13-01T00-00-00Z-a-7f3a",
        "2026-02-30T00-00-00Z-a-7f3a",
        "2026-01-01T24-00-00Z-a-7f3a",
        "2026-01-01T00-00-00Z-a-7f3a\n",
        "2026-01-01T00-00-00Z-a-7f3a/..",
        "2026-01-01T00:00:00Z-a-7f3a",
        "2026-01-01T00-00-00Z-A-7f3a",
        "2026-01-01T00-00-00Z--7f3a",
        "2026-01-01T00-00-00Z-a-7F3A",
        "٢٠٢٦-01-01T00-00-00Z-a-7f3a",
    ],
)
def test_run_id_rejects_when_value_is_malformed_or_dangerous(value: str) -> None:
    with pytest.raises(ValidationError):
        RunId(value=value)


@settings(max_examples=300, deadline=None)
@given(
    a=st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)),
    b=st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)),
)
def test_run_id_sorts_by_instant_when_created_from_random_instants(
    a: datetime, b: datetime
) -> None:
    a, b = a.replace(microsecond=0, tzinfo=UTC), b.replace(microsecond=0, tzinfo=UTC)
    ida = RunId.create(started_at=a, product="p", suffix="aaaa")
    idb = RunId.create(started_at=b, product="p", suffix="aaaa")

    assert (ida < idb) == (a < b)


def test_run_limits_rejects_bool_nan_and_zero_values() -> None:
    for kwargs in (
        {"requests_per_second": True, "max_duration_minutes": 1, "zap_threads_per_host": 1},
        {"requests_per_second": float("nan"), "max_duration_minutes": 1, "zap_threads_per_host": 1},
        {"requests_per_second": 0, "max_duration_minutes": 1, "zap_threads_per_host": 1},
        {"requests_per_second": 1, "max_duration_minutes": 0, "zap_threads_per_host": 1},
        {"requests_per_second": 1, "max_duration_minutes": 1, "zap_threads_per_host": 0},
        {"requests_per_second": 1, "max_duration_minutes": True, "zap_threads_per_host": 1},
        {"requests_per_second": 1, "max_duration_minutes": 1, "zap_threads_per_host": 1, "x": 1},
        {"requests_per_second": 51, "max_duration_minutes": 1, "zap_threads_per_host": 1},
        {"requests_per_second": 1, "max_duration_minutes": 481, "zap_threads_per_host": 1},
        {"requests_per_second": 1, "max_duration_minutes": 1, "zap_threads_per_host": 9},
    ):
        with pytest.raises(ValidationError):
            RunLimits.model_validate(kwargs)
