"""Ganchos reais do painel: diário de comandos e catálogo, sobre um diário em memória."""

from datetime import UTC, datetime, timedelta

from harness_dast.application.panel_hooks import CatalogPanelHooks
from harness_dast.domain.command_journal import JournalEntry, JournalLoad
from tests.unit.domain.panel_helpers import findings_report

RUN_1 = "2026-11-14T10-00-00Z-clinica-aaaa"
RUN_2 = "2026-11-14T12-00-00Z-clinica-bbbb"
T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


class MemoryJournal:
    def __init__(self, entries: list[JournalEntry], skipped: int = 0) -> None:
        self._entries = entries
        self._skipped = skipped

    def append(self, product: str | None, entry: JournalEntry) -> None:
        self._entries.append(entry)

    def load(self, product: str | None) -> JournalLoad:
        return JournalLoad(entries=tuple(self._entries), skipped_lines=self._skipped)


def entry(minute: int, command: str, run_id: str | None = None) -> JournalEntry:
    start = T0 + timedelta(minutes=minute)
    return JournalEntry(
        started_at=start,
        finished_at=start + timedelta(seconds=5),
        command=command,
        product="clinica",
        run_id=run_id,
        exit_code=0,
        state="ok",
    )


def test_commands_are_the_diary_slice_of_the_run_converted_for_the_panel() -> None:
    hooks = CatalogPanelHooks(
        MemoryJournal([entry(0, "doctor"), entry(1, "run", RUN_1), entry(120, "run", RUN_2)], 2)
    )

    journal = hooks.commands("clinica", RUN_1)

    assert journal is not None
    assert [item.command for item in journal.commands] == [
        "hdast doctor clinica",
        "hdast run clinica",
    ]
    assert [item.stage for item in journal.commands] == [None, "scan"]
    assert journal.skipped_lines == 2


def test_commands_is_none_when_the_diary_has_nothing_of_this_run() -> None:
    hooks = CatalogPanelHooks(MemoryJournal([entry(1, "run", RUN_1)]))

    assert hooks.commands("clinica", RUN_2) is None
    assert CatalogPanelHooks(MemoryJournal([])).commands("clinica", RUN_1) is None


def test_explanations_come_from_the_catalog_by_finding_id() -> None:
    report = findings_report()
    hooks = CatalogPanelHooks(MemoryJournal([]))

    got = hooks.explanations(report, None)

    assert set(got) == {item.finding_id for item in report.findings}


def test_explanations_are_empty_without_findings() -> None:
    assert CatalogPanelHooks(MemoryJournal([])).explanations(None, None) == {}
