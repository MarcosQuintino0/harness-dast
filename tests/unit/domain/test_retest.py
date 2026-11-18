import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.finding_diff import COMPARISON_NOTICE
from harness_dast.domain.retest import (
    RetestReport,
    build_retest_report,
    operations_of,
    reproduced_at_threshold,
    select_for_retest,
)
from tests.fakes.verification_data import finding


def _make(suffix: str, *, severity: str = "high", operation: str | None = "getPet") -> Finding:
    return finding().model_copy(
        update={
            "fingerprint": suffix * 64,
            "finding_id": f"F-{suffix * 8}",
            "proposed_severity": severity,
            "operation_id": operation,
        }
    )


def test_select_defaults_to_high_and_medium_most_severe_first_within_the_cap() -> None:
    items = [
        _make("a", severity="low"),
        _make("b", severity="medium"),
        _make("c", severity="high"),
        _make("d", severity="medium"),
    ]

    picked = select_for_retest(items, [], 2)

    assert [item.fingerprint[0] for item in picked] == ["c", "b"]


def test_select_skips_findings_without_operation_by_default() -> None:
    items = [_make("a", operation=None), _make("b")]

    assert [item.fingerprint[0] for item in select_for_retest(items, [], 10)] == ["b"]


def test_select_uses_the_chosen_fingerprints_without_repeating() -> None:
    items = [_make("a"), _make("b", severity="low")]

    picked = select_for_retest(items, ["b" * 64, "b" * 64], 10)

    assert [item.fingerprint[0] for item in picked] == ["b"]


@pytest.mark.parametrize("cap", [0, 31, -1])
def test_select_refuses_a_cap_out_of_range(cap: int) -> None:
    with pytest.raises(ConfigError) as caught:
        select_for_retest([_make("a")], [], cap)

    assert caught.value.hint


def test_select_refuses_unknown_fingerprint() -> None:
    with pytest.raises(ConfigError, match="não existem"):
        select_for_retest([_make("a")], ["z" * 64], 10)


def test_select_refuses_chosen_finding_without_operation() -> None:
    with pytest.raises(ConfigError, match="sem operação"):
        select_for_retest([_make("a", operation=None)], ["a" * 64], 10)


def test_select_refuses_when_nothing_is_eligible() -> None:
    with pytest.raises(ConfigError, match="severidade alta ou média"):
        select_for_retest([_make("a", severity="low")], [], 10)


def test_select_refuses_more_chosen_findings_than_the_cap() -> None:
    items = [_make("a"), _make("b")]

    with pytest.raises(ConfigError, match="acima do teto"):
        select_for_retest(items, ["a" * 64, "b" * 64], 1)


def test_operations_are_unique_and_keep_the_order() -> None:
    items = [_make("a", operation="x"), _make("b", operation="y"), _make("c", operation="x")]

    assert operations_of(items) == ("x", "y")


def test_operations_refuse_a_finding_without_operation() -> None:
    with pytest.raises(ConfigError):
        operations_of([_make("a", operation=None)])


def test_report_classifies_every_selected_finding_and_carries_the_notice() -> None:
    selected = [
        _make("a", operation="x"),
        _make("b", operation="y"),
        _make("c", operation="z"),
    ]

    report = build_retest_report(
        product="demo",
        previous_run_id="antes",
        run_id="depois",
        generated_at="2026-11-18T10:00:00+00:00",
        selected=selected,
        current=[selected[0]],
        scanned_operations={"x", "y"},
    )

    assert [item.result for item in report.entries] == [
        "reproduced",
        "not_reproduced",
        "not_tested",
    ]
    assert (report.counts.reproduced, report.counts.not_reproduced, report.counts.not_tested) == (
        1,
        1,
        1,
    )
    assert report.only == ("x", "y", "z")
    assert report.notice == COMPARISON_NOTICE


@pytest.mark.parametrize(
    ("threshold", "severity", "expected"),
    [
        ("high", "high", True),
        ("high", "medium", False),
        ("medium", "high", True),
        ("low", "medium", True),
        ("none", "high", False),
        ("high", "unknown", True),
    ],
)
def test_only_a_reproduced_finding_at_the_threshold_counts(
    threshold: str, severity: str, expected: bool
) -> None:
    item = _make("a", severity=severity)
    report = build_retest_report(
        product="demo",
        previous_run_id="antes",
        run_id="depois",
        generated_at="t",
        selected=[item],
        current=[item],
        scanned_operations={"getPet"},
    )

    assert reproduced_at_threshold(report, threshold) is expected


def test_a_not_reproduced_finding_never_trips_the_threshold() -> None:
    item = _make("a")
    report = build_retest_report(
        product="demo",
        previous_run_id="antes",
        run_id="depois",
        generated_at="t",
        selected=[item],
        current=[],
        scanned_operations={"getPet"},
    )

    assert reproduced_at_threshold(report, "low") is False


@pytest.mark.parametrize("raw", ['{"product":"demo"}', '{"schema_version":', "[]"])
def test_retest_report_rejects_malformed_json(raw: str) -> None:
    with pytest.raises(ValidationError):
        RetestReport.model_validate_json(raw)
