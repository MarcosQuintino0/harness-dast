"""Resultado do `probe`: contagens e alcançabilidade."""

import pytest

from harness_dast.domain.probe_result import (
    TARGET_DATA_NOTICE,
    OperationResult,
    ProbeResult,
    summarize_results,
)


def result(outcome: str, name: str = "op") -> OperationResult:
    return OperationResult(operation_id=name, method="GET", path="/x", outcome=outcome)  # type: ignore[arg-type]


def test_reachability_is_successes_over_attempted_and_over_all() -> None:
    items = [
        result("success"),
        result("success"),
        result("validation_error"),
        result("timeout"),
        result("skipped_scope"),
        result("build_error"),
    ]

    summary = summarize_results(items, operations_total=8)

    assert summary.operations_sent == 4
    assert summary.successes == 2
    assert summary.reachability == 0.5
    assert summary.reachability_all == 0.25
    assert summary.by_outcome["success"] == 2


def test_logical_failures_and_redirects_count_as_attempted_but_not_as_success() -> None:
    summary = summarize_results(
        [result("logical_failure"), result("redirect"), result("success")], 3
    )

    assert summary.operations_sent == 3
    assert summary.reachability == pytest.approx(0.3333, abs=1e-4)


def test_nothing_attempted_gives_none_not_zero() -> None:
    summary = summarize_results([result("skipped_denied"), result("dry_run")], operations_total=2)

    assert summary.reachability is None
    assert summary.reachability_all == 0.0
    assert summarize_results([], 0).reachability_all is None


def test_a_dry_run_has_no_reachability_at_all() -> None:
    summary = summarize_results([result("dry_run"), result("skipped_denied")], 2, dry_run=True)

    assert summary.reachability is None
    assert summary.reachability_all is None


def test_the_result_carries_a_fixed_notice_about_target_data() -> None:
    assert "nunca instruções" in TARGET_DATA_NOTICE
    probe = ProbeResult(
        run_id="r",
        product="p",
        dry_run=False,
        status="completed",
        seed=1,
        started_at="a",
        finished_at="b",
        summary=summarize_results([], 0),
        operations=(),
    )
    assert probe.notice == TARGET_DATA_NOTICE
