"""Testes independentes (QA) de janelas de execução e validade da autorização."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

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

SP = ZoneInfo("America/Sao_Paulo")
NY = ZoneInfo("America/New_York")
DAYS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")


def oracle_open(days: set[int], start: int, end: int, zone: ZoneInfo, now: datetime) -> bool:
    """Oráculo: relógio de parede local, aritmética ingênua dia a dia."""
    local = now.astimezone(zone).replace(tzinfo=None)
    duration = (end - start) % 1440 or 1440
    for back in (0, 1):
        day = (local - timedelta(days=back)).replace(hour=0, minute=0, second=0, microsecond=0)
        if day.weekday() not in days:
            continue
        opens = day + timedelta(minutes=start)
        if opens <= local < opens + timedelta(minutes=duration):
            return True
    return False


def at(year: int, month: int, day: int, hour: int, minute: int, zone: ZoneInfo = SP) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=zone)


# 2026-11-13 é sexta-feira.
def test_is_open_follows_spec_example_when_window_crosses_midnight() -> None:
    window = ExecutionWindow.parse("seg-sex 20:00-06:00 America/Sao_Paulo")

    assert window.is_open(at(2026, 11, 14, 3, 0))  # sábado 03:00, começou sexta
    assert not window.is_open(at(2026, 11, 16, 3, 0))  # segunda 03:00, começou domingo
    assert window.is_open(at(2026, 11, 17, 3, 0))  # terça 03:00, começou segunda
    assert window.is_open(at(2026, 11, 13, 20, 0))  # início inclusivo
    assert not window.is_open(at(2026, 11, 13, 19, 59))
    assert not window.is_open(at(2026, 11, 14, 6, 0))  # fim exclusivo
    assert window.is_open(at(2026, 11, 14, 5, 59))
    assert not window.is_open(at(2026, 11, 14, 20, 0))  # sábado 20:00 não é dia de início


def test_is_open_handles_end_of_day_when_end_is_2400() -> None:
    window = ExecutionWindow.parse("sex 00:00-24:00 America/Sao_Paulo")

    assert window.is_open(at(2026, 11, 13, 0, 0))
    assert window.is_open(at(2026, 11, 13, 23, 59))
    assert not window.is_open(at(2026, 11, 14, 0, 0))
    assert not window.is_open(at(2026, 11, 12, 23, 59))


def test_is_open_wraps_week_when_range_goes_from_friday_to_monday() -> None:
    window = ExecutionWindow.parse("sex-seg 10:00-11:00 UTC")
    utc = ZoneInfo("UTC")

    opens = [d for d in range(7) if window.is_open(datetime(2026, 11, 9 + d, 10, 30, tzinfo=utc))]
    assert opens == [0, 4, 5, 6]  # seg(9), sex(13), sab(14), dom(15)


def test_is_open_uses_utc_instant_converted_to_local_when_now_is_in_other_zone() -> None:
    window = ExecutionWindow.parse("sex 20:00-22:00 America/Sao_Paulo")

    assert window.is_open(datetime(2026, 11, 13, 23, 30, tzinfo=UTC))  # 20:30 em SP
    assert not window.is_open(datetime(2026, 11, 13, 20, 30, tzinfo=UTC))  # 17:30 em SP
    assert window.is_open(datetime(2026, 11, 13, 20, 30, tzinfo=timezone(timedelta(hours=-3))))


def test_is_open_follows_wall_clock_when_dst_starts() -> None:
    window = ExecutionWindow.parse("dom 01:00-04:00 America/New_York")
    # 2026-03-08: 02:00 locais não existe (salta para 03:00).
    assert window.is_open(datetime(2026, 3, 8, 6, 59, tzinfo=UTC))  # 01:59 EST
    assert window.is_open(datetime(2026, 3, 8, 7, 0, tzinfo=UTC))  # 03:00 EDT
    assert window.is_open(datetime(2026, 3, 8, 7, 59, tzinfo=UTC))  # 03:59 EDT
    assert not window.is_open(datetime(2026, 3, 8, 8, 0, tzinfo=UTC))  # 04:00 EDT


def test_is_open_follows_wall_clock_when_dst_ends_and_hour_repeats() -> None:
    window = ExecutionWindow.parse("dom 01:00-02:00 America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=0)
    second = datetime(2026, 11, 1, 1, 30, tzinfo=NY, fold=1)

    assert window.is_open(first)
    assert window.is_open(second)
    assert not window.is_open(datetime(2026, 11, 1, 2, 0, tzinfo=NY))


@settings(max_examples=400, deadline=None)
@given(
    days=st.sets(st.integers(0, 6), min_size=1),
    start=st.integers(0, 1439),
    end=st.integers(1, 1440),
    offset_minutes=st.integers(0, 60 * 24 * 60),
    zone=st.sampled_from([SP, NY, ZoneInfo("Europe/London"), ZoneInfo("UTC")]),
)
def test_is_open_agrees_with_wall_clock_oracle_when_inputs_are_random(
    days: set[int], start: int, end: int, offset_minutes: int, zone: ZoneInfo
) -> None:
    if start == end:
        return
    window = ExecutionWindow(
        days=frozenset(days), start_minute=start, end_minute=end, timezone=zone.key
    )
    now = datetime(2026, 2, 20, 0, 0, tzinfo=UTC) + timedelta(minutes=offset_minutes)

    assert window.is_open(now) is oracle_open(days, start, end, zone, now)


def test_is_open_raises_when_now_is_naive() -> None:
    window = ExecutionWindow.parse("seg-dom 00:00-24:00 UTC")

    with pytest.raises(ConfigError):
        window.is_open(datetime(2026, 11, 13, 12, 0))


def test_ensure_any_window_open_raises_config_error_when_now_is_naive() -> None:
    window = ExecutionWindow.parse("seg-dom 00:00-24:00 UTC")

    with pytest.raises(ConfigError):
        ensure_any_window_open((window,), datetime(2026, 11, 13, 12, 0))


def test_ensure_any_window_open_raises_scope_violation_when_there_are_no_windows() -> None:
    with pytest.raises(ScopeViolation):
        ensure_any_window_open((), datetime(2026, 11, 13, 12, 0, tzinfo=UTC))


def test_ensure_any_window_open_passes_when_only_one_of_several_is_open() -> None:
    closed = ExecutionWindow.parse("seg 00:00-01:00 UTC")
    opened = ExecutionWindow.parse("sex 00:00-24:00 UTC")

    ensure_any_window_open((closed, opened), datetime(2026, 11, 13, 12, 0, tzinfo=UTC))
    with pytest.raises(ScopeViolation):
        ensure_any_window_open((closed,), datetime(2026, 11, 13, 12, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "seg-sex",
        "seg-sex 20:00-06:00",
        "seg-sex 20:00-20:00 UTC",
        "seg-sex 00:00-00:00 UTC",
        "seg-sex 24:00-06:00 UTC",
        "seg-sex 20:60-06:00 UTC",
        "seg-sex 25:00-06:00 UTC",
        "seg-sex 20:00-24:01 UTC",
        "seg-sex 8:00-06:00 UTC",
        "seg-sex 20:00-6:00 UTC",
        "seg-sex 20h-06h UTC",
        "xxx-sex 20:00-06:00 UTC",
        "seg- 20:00-06:00 UTC",
        "-sex 20:00-06:00 UTC",
        "seg,,ter 20:00-06:00 UTC",
        "seg-sex 20:00-06:00 Nowhere/Land",
        "seg-sex 20:00-06:00 ../../etc/passwd",
        "seg-sex 20:00-06:00 /etc/localtime",
        "seg-sex 20:00-06:00 America/Sao_Paulo extra",
        "seg-sex  20:00-06:00 UTC",
        "seg-sex 20:00–06:00 UTC",
        "seg-sex ２０:00-06:00 UTC",
        "seg-sex 20:00-06:00 UTC\n",
        "seg-sex 20:00-06:00 UTC\x00",
        "segunda-sexta 20:00-06:00 UTC",
        "0-4 20:00-06:00 UTC",
    ],
)
def test_parse_raises_config_error_when_text_is_invalid(text: str) -> None:
    if text == "seg-sex 20:00-06:00 UTC\n":
        # strip() tolera quebra de linha final; é o único espaço em branco permitido nas pontas.
        ExecutionWindow.parse(text)
        return
    with pytest.raises(ConfigError):
        ExecutionWindow.parse(text)


def test_parse_accepts_uppercase_days_and_rejects_nothing_else_silently() -> None:
    window = ExecutionWindow.parse("SEG-SEX 20:00-06:00 UTC")

    assert window.days == frozenset({0, 1, 2, 3, 4})


def test_parse_error_does_not_echo_the_input() -> None:
    secret = "ZONA-SECRETA-123"

    with pytest.raises(ConfigError) as caught:
        ExecutionWindow.parse(f"seg-sex 20:00-06:00 {secret}")

    assert secret not in caught.value.message
    assert secret not in (caught.value.hint or "")


def test_execution_window_rejects_direct_construction_when_start_equals_end() -> None:
    # A especificação diz que início igual ao fim é recusado (ambíguo). A forma de dict do
    # perfil não passa por `parse`, então a regra precisa valer no próprio modelo.
    with pytest.raises(ValidationError):
        ExecutionWindow(days=frozenset({0}), start_minute=600, end_minute=600, timezone="UTC")


def test_execution_window_rejects_when_values_are_out_of_range() -> None:
    cases: tuple[dict[str, object], ...] = (
        {"days": frozenset()},
        {"days": frozenset({7})},
        {"days": frozenset({-1})},
        {"start_minute": 1440},
        {"start_minute": -1},
        {"end_minute": 0},
        {"end_minute": 1441},
        {"timezone": "../x"},
        {"timezone": "Nao/Existe"},
        {"timezone": ""},
    )
    for kwargs in cases:
        data: dict[str, object] = {
            "days": frozenset({0}),
            "start_minute": 0,
            "end_minute": 60,
            "timezone": "UTC",
        }
        data.update(kwargs)
        with pytest.raises(ValidationError):
            ExecutionWindow.model_validate(data)


# ---------------------------------------------------------------- authorization
def auth(valid_until: date) -> Authorization:
    return Authorization(reference="SEC-1", valid_until=valid_until)


def test_ensure_valid_passes_until_last_instant_of_valid_until_in_utc() -> None:
    authorization = auth(date(2026, 11, 13))

    authorization.ensure_valid(datetime(2026, 11, 13, 23, 59, 59, 999999, tzinfo=UTC))
    authorization.ensure_valid(datetime(2026, 11, 13, 0, 0, tzinfo=UTC))
    authorization.ensure_valid(datetime(2025, 1, 1, tzinfo=UTC))


def test_ensure_valid_raises_when_first_instant_after_valid_until_in_utc() -> None:
    authorization = auth(date(2026, 11, 13))

    with pytest.raises(ScopeViolation):
        authorization.ensure_valid(datetime(2026, 11, 14, 0, 0, tzinfo=UTC))


def test_ensure_valid_counts_in_utc_when_now_is_in_other_zone() -> None:
    authorization = auth(date(2026, 11, 13))
    # 22:00 em São Paulo (UTC-3) do dia 13 já é 01:00 UTC do dia 14.
    late_local = datetime(2026, 11, 13, 22, 0, tzinfo=SP)

    with pytest.raises(ScopeViolation):
        authorization.ensure_valid(late_local)
    authorization.ensure_valid(datetime(2026, 11, 14, 1, 0, tzinfo=timezone(timedelta(hours=14))))


def test_ensure_valid_raises_config_error_when_now_is_naive() -> None:
    with pytest.raises(ConfigError):
        auth(date(2099, 1, 1)).ensure_valid(datetime(2026, 11, 13, 12, 0))


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 11, 13, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 13),
        "2026-11-13T00:00:00",
        "2026-11-13T00:00:00Z",
        "13/11/2026",
        "2026-13-01",
        "2026-02-30",
        "",
        None,
        1699920000,
        True,
        "20261113",
    ],
)
def test_authorization_rejects_when_valid_until_is_not_a_plain_date(value: object) -> None:
    with pytest.raises(ValidationError):
        Authorization.model_validate({"reference": "SEC-1", "valid_until": value})


@pytest.mark.parametrize("reference", ["", " ", "\t", "a\nb", "x" * 201, "a\x00b"])
def test_authorization_rejects_when_reference_is_blank_or_not_printable(reference: str) -> None:
    with pytest.raises(ValidationError):
        Authorization.model_validate({"reference": reference, "valid_until": "2027-01-01"})
