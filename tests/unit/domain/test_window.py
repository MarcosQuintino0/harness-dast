from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError, ScopeViolation
from harness_dast.domain.window import (
    Authorization,
    ExecutionWindow,
    ensure_any_window_open,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NIGHT = "seg-sex 20:00-06:00 America/Sao_Paulo"


def at(
    year: int, month: int, day: int, hour: int, minute: int = 0, zone: ZoneInfo = SAO_PAULO
) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=zone)


# 2026-11-09 é segunda-feira; 2026-11-13 é sexta; 2026-11-14 sábado; 2026-11-15 domingo.


# --------------------------------------------------------------------------- parse


@pytest.mark.parametrize(
    ("text", "days", "start", "end"),
    [
        pytest.param(
            "seg-sex 20:00-06:00 America/Sao_Paulo", {0, 1, 2, 3, 4}, 1200, 360, id="weekdays"
        ),
        pytest.param("sab,dom 00:00-24:00 UTC", {5, 6}, 0, 1440, id="weekend_all_day"),
        pytest.param("seg-qua,sex 09:30-17:45 UTC", {0, 1, 2, 4}, 570, 1065, id="range_and_list"),
        pytest.param("sex-seg 22:00-23:00 UTC", {4, 5, 6, 0}, 1320, 1380, id="range_wrapping_week"),
        pytest.param("SEG 08:00-09:00 UTC", {0}, 480, 540, id="uppercase_day"),
        pytest.param("ter 00:00-00:01 Etc/GMT+3", {1}, 0, 1, id="zone_with_plus_sign"),
    ],
)
def test_parse_reads_compact_form_when_text_is_valid(
    text: str, days: set[int], start: int, end: int
) -> None:
    window = ExecutionWindow.parse(text)

    assert (window.days, window.start_minute, window.end_minute) == (frozenset(days), start, end)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("seg-sex", id="only_days"),
        pytest.param("seg-sex 20:00-06:00", id="missing_zone"),
        pytest.param("20:00-06:00 UTC", id="missing_days"),
        pytest.param("seg-sex 20:00 06:00 UTC", id="missing_dash"),
        pytest.param("seg-sex 8:00-06:00 UTC", id="single_digit_hour"),
        pytest.param("seg-sex 20:00-06:00  UTC", id="double_space"),
        pytest.param("seg-sex 20:00-06:00 UTC extra", id="trailing_garbage"),
        pytest.param("lun-sex 20:00-06:00 UTC", id="unknown_day_name"),
        pytest.param("seg- 20:00-06:00 UTC", id="open_range"),
        pytest.param("seg,,sex 20:00-06:00 UTC", id="empty_list_item"),
        pytest.param("seg-sex 25:00-06:00 UTC", id="hour_out_of_range"),
        pytest.param("seg-sex 20:60-06:00 UTC", id="minute_out_of_range"),
        pytest.param("seg-sex 24:00-06:00 UTC", id="start_24"),
        pytest.param("seg-sex 20:00-24:30 UTC", id="end_after_24"),
        pytest.param("seg-sex 08:00-08:00 UTC", id="start_equals_end"),
        pytest.param("seg-sex 20:00-06:00 Mars/Olympus", id="unknown_zone"),
        pytest.param("seg-sex 20:00-06:00 ../etc/passwd", id="zone_path_traversal"),
        pytest.param("seg-sex 20:00-06:00 /etc/localtime", id="zone_absolute_path"),
        pytest.param("seg-sex 20:00-06:00 America", id="zone_is_a_directory"),
    ],
)
def test_parse_raises_config_error_when_text_is_invalid(text: str) -> None:
    with pytest.raises(ConfigError) as caught:
        ExecutionWindow.parse(text)

    assert caught.value.hint


def test_window_rejects_construction_when_fields_are_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ExecutionWindow(days=frozenset({7}), start_minute=0, end_minute=60, timezone="UTC")
    with pytest.raises(ValidationError):
        ExecutionWindow(days=frozenset(), start_minute=0, end_minute=60, timezone="UTC")
    with pytest.raises(ValidationError):
        ExecutionWindow(days=frozenset({0}), start_minute=0, end_minute=0, timezone="UTC")


# ------------------------------------------------------------------------ is_open


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        pytest.param(at(2026, 11, 9, 19, 59), False, id="monday_one_minute_before_start"),
        pytest.param(at(2026, 11, 9, 20, 0), True, id="monday_at_start_is_inclusive"),
        pytest.param(at(2026, 11, 9, 23, 59), True, id="monday_before_midnight"),
        pytest.param(at(2026, 11, 10, 0, 0), True, id="tuesday_after_midnight"),
        pytest.param(at(2026, 11, 10, 5, 59), True, id="tuesday_one_minute_before_end"),
        pytest.param(at(2026, 11, 10, 6, 0), False, id="tuesday_at_end_is_exclusive"),
        pytest.param(at(2026, 11, 10, 12, 0), False, id="tuesday_noon"),
        pytest.param(at(2026, 11, 9, 3, 0), False, id="monday_early_belongs_to_sunday"),
        pytest.param(at(2026, 11, 14, 3, 0), True, id="saturday_early_belongs_to_friday"),
        pytest.param(at(2026, 11, 14, 6, 0), False, id="saturday_at_end"),
        pytest.param(at(2026, 11, 14, 22, 0), False, id="saturday_night_not_listed"),
        pytest.param(at(2026, 11, 13, 23, 0), True, id="friday_night"),
        pytest.param(at(2026, 11, 15, 3, 0), False, id="sunday_early_after_saturday_not_listed"),
    ],
)
def test_is_open_follows_window_when_it_crosses_midnight(when: datetime, expected: bool) -> None:
    window = ExecutionWindow.parse(NIGHT)

    assert window.is_open(when) is expected


def test_is_open_does_not_cross_midnight_when_start_is_before_end() -> None:
    window = ExecutionWindow.parse("seg 09:00-17:00 America/Sao_Paulo")

    assert window.is_open(at(2026, 11, 9, 9, 0))
    assert window.is_open(at(2026, 11, 9, 16, 59))
    assert not window.is_open(at(2026, 11, 9, 17, 0))
    assert not window.is_open(at(2026, 11, 10, 10, 0))


def test_is_open_covers_the_whole_day_when_window_is_00_00_to_24_00() -> None:
    window = ExecutionWindow.parse("qua 00:00-24:00 UTC")

    assert window.is_open(datetime(2026, 11, 11, 0, 0, tzinfo=UTC))
    assert window.is_open(datetime(2026, 11, 11, 23, 59, tzinfo=UTC))
    assert not window.is_open(datetime(2026, 11, 12, 0, 0, tzinfo=UTC))
    assert not window.is_open(datetime(2026, 11, 10, 23, 59, tzinfo=UTC))


def test_is_open_converts_instant_to_window_zone_when_now_is_in_another_zone() -> None:
    window = ExecutionWindow.parse(NIGHT)
    utc_instant = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)  # 22:00 de segunda em São Paulo

    assert window.is_open(utc_instant)
    assert not window.is_open(utc_instant + timedelta(hours=9))


def test_is_open_raises_config_error_when_now_is_naive() -> None:
    window = ExecutionWindow.parse(NIGHT)

    with pytest.raises(ConfigError, match="sem fuso"):
        window.is_open(datetime(2026, 11, 9, 21, 0))


# ------------------------------------------------------------- horário de verão (EUA)


def test_is_open_uses_wall_clock_when_spring_forward_skips_an_hour() -> None:
    window = ExecutionWindow.parse("dom 01:00-03:00 America/New_York")

    assert window.is_open(datetime(2026, 3, 8, 6, 59, tzinfo=UTC))  # 01:59 EST
    assert not window.is_open(datetime(2026, 3, 8, 7, 0, tzinfo=UTC))  # 03:00 EDT, fecha
    assert not window.is_open(datetime(2026, 3, 8, 5, 59, tzinfo=UTC))  # 00:59 EST


def test_is_open_stays_open_through_both_repeated_hours_when_fall_back_repeats_one() -> None:
    window = ExecutionWindow.parse("dom 01:00-03:00 America/New_York")

    assert window.is_open(datetime(2026, 11, 1, 5, 0, tzinfo=UTC))  # 01:00 EDT
    assert window.is_open(datetime(2026, 11, 1, 6, 30, tzinfo=UTC))  # 01:30 EST (repetida)
    assert window.is_open(datetime(2026, 11, 1, 7, 59, tzinfo=UTC))  # 02:59 EST
    assert not window.is_open(datetime(2026, 11, 1, 8, 0, tzinfo=UTC))  # 03:00 EST


def test_is_open_closes_at_local_end_when_night_window_crosses_a_dst_change() -> None:
    window = ExecutionWindow.parse("sab 22:00-06:00 America/New_York")

    assert window.is_open(datetime(2026, 3, 8, 9, 59, tzinfo=UTC))  # 05:59 EDT de domingo
    assert not window.is_open(datetime(2026, 3, 8, 10, 0, tzinfo=UTC))  # 06:00 EDT


def _oracle_is_open(window: ExecutionWindow, now: datetime) -> bool:
    """Oráculo independente: olha o dia de início (hoje e ontem) em relógio de parede local."""
    local = now.astimezone(ZoneInfo(window.timezone))
    minute = local.hour * 60 + local.minute
    yesterday = (local.weekday() - 1) % 7
    if window.start_minute < window.end_minute:
        return local.weekday() in window.days and window.start_minute <= minute < window.end_minute
    started_today = local.weekday() in window.days and minute >= window.start_minute
    started_yesterday = yesterday in window.days and minute < window.end_minute
    return started_today or started_yesterday


_INSTANTS = st.datetimes(
    min_value=datetime(2025, 1, 1),
    max_value=datetime(2027, 12, 31),
    timezones=st.just(UTC),
)


@settings(max_examples=500, deadline=None)
@given(
    instant=_INSTANTS,
    days=st.sets(st.integers(0, 6), min_size=1),
    start=st.integers(0, 1439),
    end=st.integers(1, 1439),
    zone=st.sampled_from(["America/New_York", "America/Sao_Paulo", "Europe/London", "Asia/Tokyo"]),
)
def test_is_open_matches_independent_oracle_when_window_and_instant_are_random(
    instant: datetime, days: set[int], start: int, end: int, zone: str
) -> None:
    if start == end:
        return
    window = ExecutionWindow(
        days=frozenset(days), start_minute=start, end_minute=end, timezone=zone
    )

    assert window.is_open(instant) is _oracle_is_open(window, instant)


@settings(max_examples=300, deadline=None)
@given(instant=_INSTANTS, offset=st.integers(-12, 14))
def test_is_open_is_independent_of_the_zone_used_to_express_the_instant(
    instant: datetime, offset: int
) -> None:
    window = ExecutionWindow.parse("seg-sex 20:00-06:00 America/New_York")
    same_instant = instant.astimezone(timezone(timedelta(hours=offset)))

    assert window.is_open(same_instant) is window.is_open(instant)


# ----------------------------------------------------------------- várias janelas


def test_ensure_any_window_open_passes_when_one_of_several_windows_is_open() -> None:
    windows = (
        ExecutionWindow.parse(NIGHT),
        ExecutionWindow.parse("sab 10:00-12:00 America/Sao_Paulo"),
    )

    ensure_any_window_open(windows, at(2026, 11, 14, 11, 0))


def test_ensure_any_window_open_raises_scope_violation_when_all_are_closed() -> None:
    windows = (ExecutionWindow.parse(NIGHT),)

    with pytest.raises(ScopeViolation, match="fechada") as caught:
        ensure_any_window_open(windows, at(2026, 11, 10, 12, 0))

    assert caught.value.hint


def test_ensure_any_window_open_fails_closed_when_there_are_no_windows() -> None:
    with pytest.raises(ScopeViolation):
        ensure_any_window_open((), at(2026, 11, 10, 12, 0))


def test_ensure_any_window_open_raises_config_error_when_now_is_naive() -> None:
    with pytest.raises(ConfigError):
        ensure_any_window_open((ExecutionWindow.parse(NIGHT),), datetime(2026, 11, 10, 12, 0))


# ------------------------------------------------------------------ autorização


def make_authorization() -> Authorization:
    return Authorization(reference="SEC-1234", valid_until=date(2027, 1, 31))


def test_authorization_is_valid_on_its_last_day_in_utc() -> None:
    make_authorization().ensure_valid(datetime(2027, 1, 31, 23, 59, 59, tzinfo=UTC))


def test_authorization_expires_when_utc_day_is_after_valid_until() -> None:
    with pytest.raises(ScopeViolation, match="expirou") as caught:
        make_authorization().ensure_valid(datetime(2027, 2, 1, 0, 0, tzinfo=UTC))

    assert "SEC-1234" in caught.value.message
    assert caught.value.hint


def test_authorization_expires_in_utc_even_when_local_day_is_still_the_last_one() -> None:
    # 22:00 de 31/01 em São Paulo já é 01:00 de 01/02 em UTC: fecha para o lado seguro.
    with pytest.raises(ScopeViolation):
        make_authorization().ensure_valid(at(2027, 1, 31, 22, 0))


def test_authorization_raises_config_error_when_now_is_naive() -> None:
    with pytest.raises(ConfigError):
        make_authorization().ensure_valid(datetime(2027, 1, 1))


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"reference": "", "valid_until": date(2027, 1, 1)}, id="empty_reference"),
        pytest.param({"reference": "   ", "valid_until": date(2027, 1, 1)}, id="blank_reference"),
        pytest.param({"reference": "A\x00B", "valid_until": date(2027, 1, 1)}, id="control_char"),
        pytest.param({"reference": "X" * 201, "valid_until": date(2027, 1, 1)}, id="too_long"),
        pytest.param({"reference": "SEC-1"}, id="missing_valid_until"),
        pytest.param({"reference": "SEC-1", "valid_until": "amanhã"}, id="not_a_date"),
        pytest.param({"reference": "SEC-1", "valid_until": None}, id="null_date"),
        pytest.param(
            {"reference": "SEC-1", "valid_until": datetime(2027, 1, 1, 12, 0)},
            id="datetime_instead_of_date",
        ),
        pytest.param({"valid_until": date(2027, 1, 1)}, id="missing_reference"),
        pytest.param(
            {"reference": "SEC-1", "valid_until": date(2027, 1, 1), "extra": 1}, id="extra_field"
        ),
    ],
)
def test_authorization_rejects_construction_when_data_is_invalid(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Authorization.model_validate(data)


def test_authorization_accepts_iso_date_string_when_parsed_from_yaml_like_data() -> None:
    parsed = Authorization.model_validate({"reference": "SEC-1", "valid_until": "2027-01-31"})

    assert parsed.valid_until == date(2027, 1, 31)


@pytest.mark.parametrize("value", ["2026-11-13", date(2026, 11, 13)])
def test_authorization_accepts_plain_date_when_valid_until_is_date_or_iso_text(
    value: object,
) -> None:
    auth = Authorization.model_validate({"reference": "SEC-1", "valid_until": value})

    assert auth.valid_until == date(2026, 11, 13)


@pytest.mark.parametrize("value", [True, 20261113, b"2026-11-13", "13/11/2026", "2026-11-13 "])
def test_authorization_rejects_when_valid_until_is_not_date_or_iso_text(value: object) -> None:
    with pytest.raises(ValidationError):
        Authorization.model_validate({"reference": "SEC-1", "valid_until": value})
