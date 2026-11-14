"""Soma das regras do ZAP por varredura (ADR 0031)."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.rule_stats import RuleStat, total_rules


def rule(plugin_id: int, state: str = "completed", /, **changes: Any) -> RuleStat:
    base: dict[str, object] = {
        "plugin_id": plugin_id,
        "name": f"Regra {plugin_id}",
        "state": state,
        "time_ms": 100,
        "requests": 4,
        "alerts": 1,
    }
    return RuleStat.model_validate({**base, **changes})


def test_totals_add_time_requests_and_alerts_across_operations() -> None:
    totals = total_rules([[rule(1), rule(2)], [rule(1, time_ms=50, requests=6, alerts=0)]])

    first = next(item for item in totals if item.plugin_id == 1)
    assert (first.time_ms, first.requests, first.alerts, first.operations) == (150, 10, 1, 2)
    assert first.completed == 2


def test_totals_are_sorted_from_the_slowest_with_the_id_breaking_ties() -> None:
    totals = total_rules([[rule(7, time_ms=10), rule(5, time_ms=900), rule(3, time_ms=10)]])

    assert [item.plugin_id for item in totals] == [5, 3, 7]


def test_totals_count_each_state_and_treat_a_missing_time_as_zero_in_the_sum() -> None:
    totals = total_rules(
        [[rule(1, "skipped", time_ms=None)], [rule(1, "interrupted")], [rule(1, "pending")]]
    )

    (only,) = totals
    assert (only.skipped, only.interrupted, only.pending, only.completed) == (1, 1, 1, 0)
    assert only.time_ms == 200
    assert only.operations == 3


def test_no_operations_means_no_totals() -> None:
    assert total_rules([]) == ()
    assert total_rules([[]]) == ()


@pytest.mark.parametrize("field", ["time_ms", "requests", "alerts"])
def test_negative_numbers_are_refused(field: str) -> None:
    with pytest.raises(ValidationError):
        rule(1, **{field: -1})


def test_a_negative_plugin_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        RuleStat(plugin_id=-1, name="x", state="completed")


def test_a_state_outside_the_closed_list_is_refused() -> None:
    with pytest.raises(ValidationError):
        rule(1, "terminou")
