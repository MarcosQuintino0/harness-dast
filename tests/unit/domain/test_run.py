import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import (
    MAX_DURATION_MINUTES,
    MAX_REQUESTS_PER_SECOND,
    MAX_ZAP_THREADS_PER_HOST,
    RunId,
    RunLimits,
)

STARTED = datetime(2026, 11, 12, 21, 4, 11, tzinfo=UTC)


def test_create_builds_documented_format_when_inputs_are_valid() -> None:
    run_id = RunId.create(started_at=STARTED, product="agenda", suffix="7f3a")

    assert str(run_id) == "2026-11-12T21-04-11Z-agenda-7f3a"


def test_create_converts_to_utc_when_instant_has_another_offset() -> None:
    local = datetime(2026, 11, 12, 18, 4, 11, tzinfo=timezone(timedelta(hours=-3)))

    run_id = RunId.create(started_at=local, product="agenda", suffix="7f3a")

    assert run_id.value.startswith("2026-11-12T21-04-11Z-")


def test_create_is_deterministic_when_called_twice_with_same_arguments() -> None:
    first = RunId.create(started_at=STARTED, product="agenda", suffix="7f3a")
    second = RunId.create(started_at=STARTED, product="agenda", suffix="7f3a")

    assert first == second


def test_ids_sort_by_time_when_compared_as_text_or_objects() -> None:
    earlier = RunId.create(started_at=STARTED, product="zeta", suffix="ffff")
    later = RunId.create(started_at=STARTED + timedelta(seconds=1), product="alfa", suffix="0000")

    assert earlier < later
    assert earlier.value < later.value
    assert sorted([later, earlier]) == [earlier, later]


def test_create_raises_config_error_when_instant_is_naive() -> None:
    with pytest.raises(ConfigError):
        RunId.create(started_at=datetime(2026, 11, 12, 21, 4, 11), product="a", suffix="7f3a")


@pytest.mark.parametrize(
    "product", ["", "Agenda", "a b", "a/b", "a..b", "a_b", "-a", "a-", "x" * 41, "á"]
)
def test_create_rejects_product_when_slug_is_invalid(product: str) -> None:
    with pytest.raises(ValueError, match="produto"):
        RunId.create(started_at=STARTED, product=product, suffix="7f3a")


@pytest.mark.parametrize("suffix", ["", "abc", "ABCD", "7f3g", "7f3a7f3a7", "../..", "7f 3a"])
def test_create_rejects_suffix_when_it_is_not_short_lowercase_hex(suffix: str) -> None:
    with pytest.raises(ValueError, match="sufixo"):
        RunId.create(started_at=STARTED, product="agenda", suffix=suffix)


def test_run_id_contains_only_filesystem_safe_characters_when_created() -> None:
    run_id = RunId.create(started_at=STARTED, product="agenda-2", suffix="7f3a")

    assert set(run_id.value) <= set("0123456789abcdefghijklmnopqrstuvwxyz-TZ")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "agenda",
        "../../etc/passwd",
        "2026-11-12T21-04-11Z-agenda",
        "2026-11-12T21:04:11Z-agenda-7f3a",
        "2026-11-12T21-04-11Z-Agenda-7f3a",
        "2026-11-12T21-04-11Z-agenda-7F3A",
        "2026-13-12T21-04-11Z-agenda-7f3a",
        "2026-11-31T21-04-11Z-agenda-7f3a",
        "2026-11-12T25-04-11Z-agenda-7f3a",
        "2026-11-12T21-04-11Z-agenda-7f3a/../x",
        "2026-11-12T21-04-11Z-agenda-7f3a\n",
        "x" * 101,
    ],
)
def test_run_id_rejects_construction_when_value_is_malformed(value: str) -> None:
    with pytest.raises(ValidationError):
        RunId(value=value)


def test_run_id_accepts_existing_value_when_parsed_back_from_text() -> None:
    assert (
        RunId(value="2026-11-12T21-04-11Z-agenda-7f3a").value == "2026-11-12T21-04-11Z-agenda-7f3a"
    )


# ---------------------------------------------------------------------- limites


def make_limits(**changes: object) -> RunLimits:
    data: dict[str, object] = {
        "requests_per_second": 5,
        "max_duration_minutes": 60,
        "zap_threads_per_host": 2,
    }
    data.update(changes)
    return RunLimits.model_validate(data)


def test_limits_accept_values_when_inside_bounds() -> None:
    limits = make_limits()

    assert (
        limits.requests_per_second,
        limits.max_duration_minutes,
        limits.zap_threads_per_host,
    ) == (
        5,
        60,
        2,
    )


def test_limits_accept_fractional_rate_when_below_one_request_per_second() -> None:
    assert make_limits(requests_per_second=0.5).requests_per_second == 0.5


def test_limits_accept_hard_maxima_when_values_equal_the_constants() -> None:
    limits = make_limits(
        requests_per_second=MAX_REQUESTS_PER_SECOND,
        max_duration_minutes=MAX_DURATION_MINUTES,
        zap_threads_per_host=MAX_ZAP_THREADS_PER_HOST,
    )

    assert limits.max_duration_minutes == MAX_DURATION_MINUTES


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"requests_per_second": 0}, id="rps_zero"),
        pytest.param({"requests_per_second": -1}, id="rps_negative"),
        pytest.param({"requests_per_second": MAX_REQUESTS_PER_SECOND + 0.1}, id="rps_over_max"),
        pytest.param({"requests_per_second": math.nan}, id="rps_nan"),
        pytest.param({"requests_per_second": math.inf}, id="rps_inf"),
        pytest.param({"requests_per_second": "5"}, id="rps_string"),
        pytest.param({"requests_per_second": True}, id="rps_bool"),
        pytest.param({"requests_per_second": None}, id="rps_none"),
        pytest.param({"max_duration_minutes": 0}, id="duration_zero"),
        pytest.param({"max_duration_minutes": -5}, id="duration_negative"),
        pytest.param({"max_duration_minutes": MAX_DURATION_MINUTES + 1}, id="duration_over_max"),
        pytest.param({"max_duration_minutes": 1.5}, id="duration_float"),
        pytest.param({"max_duration_minutes": "60"}, id="duration_string"),
        pytest.param({"max_duration_minutes": True}, id="duration_bool"),
        pytest.param({"zap_threads_per_host": 0}, id="threads_zero"),
        pytest.param({"zap_threads_per_host": MAX_ZAP_THREADS_PER_HOST + 1}, id="threads_over_max"),
        pytest.param({"zap_threads_per_host": 2.0}, id="threads_float"),
        pytest.param({"unknown_limit": 1}, id="extra_field"),
    ],
)
def test_limits_reject_when_value_is_out_of_bounds_or_wrong_type(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        make_limits(**changes)


@pytest.mark.parametrize(
    "missing", ["requests_per_second", "max_duration_minutes", "zap_threads_per_host"]
)
def test_limits_reject_when_a_field_is_missing(missing: str) -> None:
    data: dict[str, object] = {
        "requests_per_second": 5,
        "max_duration_minutes": 60,
        "zap_threads_per_host": 2,
    }
    del data[missing]

    with pytest.raises(ValidationError):
        RunLimits.model_validate(data)


def test_limits_are_frozen_when_assignment_is_attempted() -> None:
    limits = make_limits()

    with pytest.raises(ValidationError):
        limits.requests_per_second = 500  # type: ignore[misc]  # prova que o modelo é congelado


def test_run_limits_hard_maxima_are_pinned_when_checked_at_the_boundary() -> None:
    # Fixa os valores dos tetos duros (mutantes M20, M31, M32 do QA): no teto passa, acima falha.
    at_max = {"requests_per_second": 50, "max_duration_minutes": 480, "zap_threads_per_host": 8}
    assert RunLimits.model_validate(at_max).requests_per_second == 50

    for field, above in (
        ("requests_per_second", 50.5),
        ("max_duration_minutes", 481),
        ("zap_threads_per_host", 9),
    ):
        with pytest.raises(ValidationError):
            RunLimits.model_validate({**at_max, field: above})
