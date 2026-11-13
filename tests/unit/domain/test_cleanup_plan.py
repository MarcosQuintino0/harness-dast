"""Plano, teto de linhas e fim da execução."""

from datetime import UTC, datetime, timedelta

import pytest

from harness_dast.domain.cleanup_plan import (
    CleanupPlan,
    StatementResult,
    ensure_within_ceiling,
    run_is_finished,
)
from harness_dast.domain.errors import CleanupError

START = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def test_plan_total_is_the_sum_of_rows() -> None:
    plan = CleanupPlan(
        product="p",
        run_id="r",
        script_sha256="h",
        results=(
            StatementResult(index=1, table="A", rows=3),
            StatementResult(index=2, table="B", rows=4),
        ),
        max_rows=10,
    )

    assert plan.total_rows == 7


def test_ceiling_allows_total_equal_to_the_limit_and_refuses_one_more() -> None:
    ensure_within_ceiling(10, 10, source="cleanup.max_rows")

    with pytest.raises(CleanupError) as caught:
        ensure_within_ceiling(11, 10, source="cleanup.max_rows")

    assert "11" in caught.value.message
    assert "cleanup.max_rows" in caught.value.message
    assert caught.value.hint is not None
    assert "ROLLBACK" in caught.value.hint


def test_run_with_finished_at_is_finished_even_inside_its_deadline() -> None:
    assert run_is_finished(
        finished_at="2026-11-12T10:05:00+00:00",
        started_at=START,
        max_duration_minutes=60,
        now=START + timedelta(minutes=6),
    )


def test_running_run_is_not_finished_until_its_deadline_passes() -> None:
    before = START + timedelta(minutes=59, seconds=59)
    after = START + timedelta(minutes=60)

    assert not run_is_finished(
        finished_at=None, started_at=START, max_duration_minutes=60, now=before
    )
    assert run_is_finished(finished_at=None, started_at=START, max_duration_minutes=60, now=after)
