"""Contrato das variáveis de ligação."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from harness_dast.domain.cleanup_binds import (
    allowed_bind_names,
    build_binds,
    parse_run_start,
    select_binds,
)
from harness_dast.domain.errors import ConfigError

RUN_ID = "2026-11-12T21-04-11Z-agenda-7f3a"


def test_allowed_names_are_the_static_ones_plus_one_per_account() -> None:
    assert allowed_bind_names(2) == {"run_start", "run_id", "run_tag", "account_1", "account_2"}
    assert allowed_bind_names(0) == {"run_start", "run_id", "run_tag"}


def test_build_binds_converts_start_to_naive_utc_and_extracts_the_tag() -> None:
    brasilia = timezone(timedelta(hours=-3))
    started = datetime(2026, 11, 12, 18, 4, 11, tzinfo=brasilia)

    binds = build_binds(run_id=RUN_ID, started_at=started, usernames=["ana", "beto"])

    assert binds == {
        "run_start": datetime(2026, 11, 12, 21, 4, 11),
        "run_id": RUN_ID,
        "run_tag": "7f3a",
        "account_1": "ana",
        "account_2": "beto",
    }
    start = binds["run_start"]
    assert isinstance(start, datetime)
    assert start.tzinfo is None


def test_build_binds_rejects_a_start_without_timezone() -> None:
    with pytest.raises(ConfigError):
        build_binds(run_id=RUN_ID, started_at=datetime(2026, 11, 12), usernames=[])


def test_select_binds_returns_only_the_requested_names() -> None:
    binds = build_binds(run_id=RUN_ID, started_at=datetime(2026, 1, 1, tzinfo=UTC), usernames=["a"])

    assert select_binds(binds, ["run_id", "account_1"]) == {"run_id": RUN_ID, "account_1": "a"}


def test_parse_run_start_returns_utc_and_rejects_malformed_or_naive_text() -> None:
    parsed = parse_run_start("2026-11-12T18:04:11-03:00")

    assert parsed == datetime(2026, 11, 12, 21, 4, 11, tzinfo=UTC)
    with pytest.raises(ConfigError):
        parse_run_start("ontem")
    with pytest.raises(ConfigError):
        parse_run_start("2026-11-12T18:04:11")
