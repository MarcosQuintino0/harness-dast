"""Linhas dos índices: o que rodou, comparação entre testes do mesmo tipo, sem dado."""

from datetime import UTC, datetime

from harness_dast.domain.panel.index_build import (
    diff,
    empty_row,
    is_sweep,
    longest_open,
    make_entry,
    previous_of,
    row_from_sources,
)
from harness_dast.domain.panel.index_model import ProductInfo, RowFinding, RunRow
from harness_dast.domain.run_summary import StageRecord
from tests.unit.domain.panel.helpers import PRODUCT, bare, run_summary, sources

BEGIN = datetime(2026, 11, 13, 20, 8, tzinfo=UTC)


def make_row(run_id: str, ids: tuple[str, ...] | None = (), *, kind: str = "scan") -> RunRow:
    """Linha pronta; `ids=None` é teste sem relatório de falhas."""
    return RunRow(
        run_id=run_id,
        product=PRODUCT,
        state="ok",
        started_at=BEGIN,
        kind=kind,  # type: ignore[arg-type]  # o literal é conferido pelo modelo
        what_ran="Varredura completa",
        verdict="finished",
        severe_count=None if ids is None else len(ids),
        severe=tuple(RowFinding(finding_id=item, title=f"falha {item}") for item in ids or ()),
    )


def test_a_full_run_row_says_what_ran_and_counts_the_severe_findings() -> None:
    row = row_from_sources(sources(), incomplete=False, panel_link=None)

    assert row.state == "ok"
    assert row.kind == "scan"
    assert row.what_ran == "Varredura completa"
    assert row.verdict == "finished"
    assert row.severe_count == 1
    assert row.severe[0].finding_id.startswith("F-")
    assert row.functions_attacked == 1
    assert row.tokens is None


def test_an_incomplete_read_marks_the_row_partial_and_keeps_the_rest() -> None:
    row = row_from_sources(sources(), incomplete=True, panel_link="x/panel/summary.html")

    assert row.state == "partial"
    assert row.panel_link == "x/panel/summary.html"
    assert row.severe_count == 1


def test_a_run_that_only_conferred_is_only_a_conference() -> None:
    stages = (
        StageRecord(name="preflight", status="ok", duration_seconds=10.0),
        StageRecord(name="probe", status="not_run"),
        StageRecord(name="scan", status="not_run"),
        StageRecord(name="authz", status="not_run"),
        StageRecord(name="report", status="not_run"),
    )
    src = sources(summary=run_summary(stages=stages, status="failed"), scan=None, findings=None)

    row = row_from_sources(src, incomplete=False, panel_link=None)

    assert (row.kind, row.what_ran) == ("preflight", "Só conferência")
    assert row.severe_count is None


def test_a_run_with_the_probe_only_is_a_probe_only() -> None:
    stages = (
        StageRecord(name="preflight", status="ok"),
        StageRecord(name="probe", status="ok"),
        StageRecord(name="scan", status="skipped"),
        StageRecord(name="authz", status="skipped"),
        StageRecord(name="report", status="skipped"),
    )
    src = sources(summary=run_summary(stages=stages), scan=None, findings=None)

    assert row_from_sources(src, incomplete=False, panel_link=None).what_ran == "Só alcance"


def test_the_empty_row_keeps_the_date_and_says_nothing_else() -> None:
    row = empty_row("2026-11-13T20-08-00Z-vampi-ab12", PRODUCT, BEGIN, None)

    assert row.state == "empty"
    assert row.severe_count is None
    assert row.what_ran is None
    assert row.verdict is None


def test_a_bare_run_still_builds_a_row_without_inventing_numbers() -> None:
    row = row_from_sources(bare(), incomplete=False, panel_link=None)

    assert row.severe_count is None
    assert row.functions_attacked is None
    assert row.duration_seconds is None


def test_entries_are_ordered_from_the_newest_run_to_the_oldest() -> None:
    entry = make_entry(PRODUCT, ProductInfo(), [make_row("2026-11-12"), make_row("2026-11-13")])

    assert [row.run_id for row in entry.rows] == ["2026-11-13", "2026-11-12"]
    assert entry.name == "Vampi"


def test_the_diff_counts_new_persistent_and_not_seen_by_the_finding_code() -> None:
    before = make_row("a", ("F-1", "F-2", "F-3"))
    now = make_row("b", ("F-2", "F-3", "F-4"))

    change = diff(before, now)

    assert change is not None
    assert (change.new, change.persistent, change.gone) == (1, 2, 1)
    assert change.gone_items == ("falha F-1",)
    assert change.new_items == ("falha F-4",)


def test_the_diff_is_none_when_one_side_has_no_findings_report() -> None:
    assert diff(make_row("a", None), make_row("b", ("F-1",))) is None
    assert diff(make_row("a", ("F-1",)), make_row("b", None)) is None


def test_the_previous_test_is_the_next_older_one_of_the_same_kind() -> None:
    rows = [
        make_row("c", ("F-1",), kind="authz"),
        make_row("b", ("F-1",), kind="scan"),
        make_row("a", ("F-1",), kind="authz"),
    ]

    assert previous_of(rows, 0) is rows[2]
    assert previous_of(rows, 1) is None


def test_an_empty_row_is_never_the_previous_test() -> None:
    rows = [make_row("b", ("F-1",)), empty_row("a", PRODUCT, BEGIN, None)]

    assert previous_of(rows, 0) is None


def test_the_oldest_open_findings_need_two_tests_in_a_row_and_sort_by_age() -> None:
    rows = [
        make_row("c", ("F-1", "F-2", "F-3")),
        make_row("b", ("F-1", "F-2")),
        make_row("a", ("F-1",)),
    ]

    found = longest_open(rows)

    assert [(item.title, item.tests) for item in found] == [("falha F-1", 3), ("falha F-2", 2)]


def test_a_finding_that_went_away_and_came_back_counts_only_the_last_streak() -> None:
    rows = [make_row("c", ("F-1",)), make_row("b", ()), make_row("a", ("F-1",))]

    assert longest_open(rows) == ()


def test_only_sweeps_with_a_report_enter_the_chart() -> None:
    assert is_sweep(make_row("a", ("F-1",)))
    assert not is_sweep(make_row("a", None))
    assert not is_sweep(make_row("a", (), kind="probe"))
