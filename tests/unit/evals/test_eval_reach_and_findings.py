"""Regress?es da r?gua de alcance da V1.5.4."""

from pathlib import Path

import pytest

from evals.runner.checks_reach import reach_component, read_probes
from evals.runner.checks_triage import triage_component
from tests.unit.evals.support import write_json


@pytest.mark.parametrize(("successes", "rejections", "errors"), [(2, 1, 1), (4, 2, 2)])
def test_expected_login_rejection_counts_as_reached_without_counting_as_success(
    tmp_path: Path, successes: int, rejections: int, errors: int
) -> None:
    total = successes + rejections + errors
    write_json(
        tmp_path / "runs/r/probe.json",
        {
            "finished_at": "2026-01-01",
            "summary": {
                "operations_total": total,
                "operations_sent": total,
                "successes": successes,
                "by_outcome": {
                    "success": successes,
                    "auth_rejected_expected": rejections,
                    "auth_error": errors,
                },
            },
        },
    )

    probe = read_probes(tmp_path)[0]

    assert probe.successes == successes
    assert probe.effective == pytest.approx((successes + rejections) / total)
    assert reach_component(tmp_path).score == pytest.approx(probe.effective / 0.9)


def test_findings_in_another_run_keep_finding_checks_applicable(tmp_path: Path) -> None:
    write_json(tmp_path / "runs/first/triage.json", {"annotations": []})
    write_json(tmp_path / "runs/second/findings.json", {"findings": []})

    component = triage_component(tmp_path)

    assert all(check.passed is not None for check in component.checks)
