from datetime import UTC, datetime, timedelta

from harness_dast.application.command_journal import load_journal_for_run
from harness_dast.domain.command_journal import JournalEntry, JournalLoad

RUN_1 = "2026-11-14T10-00-00Z-clinica-aaaa"
RUN_2 = "2026-11-14T12-00-00Z-clinica-bbbb"
T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


class _MemoryJournal:
    def __init__(self, entries: list[JournalEntry], skipped: int = 0) -> None:
        self._entries = entries
        self._skipped = skipped
        self.asked: list[str | None] = []

    def append(self, product: str | None, entry: JournalEntry) -> None:
        self._entries.append(entry)

    def load(self, product: str | None) -> JournalLoad:
        self.asked.append(product)
        return JournalLoad(entries=tuple(self._entries), skipped_lines=self._skipped)


def _entry(minute: int, command: str, run_id: str | None = None) -> JournalEntry:
    start = T0 + timedelta(minutes=minute)
    return JournalEntry(
        started_at=start,
        finished_at=start,
        command=command,
        run_id=run_id,
        exit_code=0,
        state="ok",
    )


def test_load_journal_for_run_devolve_o_trecho_do_teste_do_produto() -> None:
    store = _MemoryJournal(
        [
            _entry(0, "doctor"),
            _entry(1, "run", RUN_1),
            _entry(120, "doctor"),
            _entry(121, "run", RUN_2),
        ]
    )

    got = load_journal_for_run(store, "clinica", RUN_2)

    assert [e.command for e in got.entries] == ["doctor", "run"]
    assert store.asked == ["clinica"]


def test_load_journal_for_run_com_linhas_puladas_ainda_devolve_o_que_leu() -> None:
    store = _MemoryJournal([_entry(1, "run", RUN_1)], skipped=3)

    got = load_journal_for_run(store, "clinica", RUN_1)

    assert len(got.entries) == 1
    assert got.skipped_lines == 3


def test_load_journal_for_run_diz_se_o_diario_existe_mesmo_sem_comando_do_teste() -> None:
    assert load_journal_for_run(_MemoryJournal([_entry(1, "doctor")]), "clinica", RUN_2).has_diary
    assert not load_journal_for_run(_MemoryJournal([]), "clinica", RUN_2).has_diary


def test_load_journal_for_run_sem_diario_devolve_vazio() -> None:
    assert load_journal_for_run(_MemoryJournal([]), "clinica", RUN_1).entries == ()
