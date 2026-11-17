"""Índices do painel: pasta vazia, execução corrompida, dois produtos e o envoltório do painel."""

from datetime import UTC, datetime

import pytest

from harness_dast.application.panel import PanelOutcome, PanelRequest
from harness_dast.application.panel_index import IndexedPanel, PanelIndexer
from harness_dast.domain.errors import ConfigError
from tests.fakes.clock import FixedClock
from tests.fakes.panel_index_ports import BreakableFiles, FakeIndexFiles
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.unit.domain.panel.helpers import findings_report, run_summary, sources

OLD = "2026-11-12T20-08-00Z-vampi-ab12"
NEW = "2026-11-13T20-08-00Z-vampi-cd34"
OTHER = "2026-11-13T09-00-00Z-clinica-piloto-ef56"


class Rig:
    def __init__(self) -> None:
        self.files = BreakableFiles()
        self.index_files = FakeIndexFiles()
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(valid_profile("vampi"))
        self.clock = FixedClock(datetime(2026, 11, 14, 12, 0, tzinfo=UTC))

    def indexer(self) -> PanelIndexer:
        return PanelIndexer(
            files=self.files,
            index_files=self.index_files,
            profiles=self.profiles,
            clock=self.clock,
            timezone=UTC,
        )

    def add_run(self, run_id: str, product: str, *, panel: bool = True) -> None:
        base = sources()
        self.index_files.add(run_id, product, panel=panel)
        self.files.summary[run_id] = run_summary(product=product, run_id=run_id)
        self.files.probe[run_id] = base.probe  # type: ignore[assignment]
        self.files.scan[run_id] = base.scan  # type: ignore[assignment]
        self.files.findings[run_id] = findings_report()


def test_with_an_empty_runs_folder_the_index_says_no_product_and_writes_no_history() -> None:
    rig = Rig()

    written = rig.indexer().rebuild()

    assert written == ("index.html",)
    assert "Nenhum produto testado ainda" in rig.index_files.written["index.html"]


def test_two_products_get_the_index_and_one_history_each() -> None:
    rig = Rig()
    rig.add_run(OLD, "vampi")
    rig.add_run(NEW, "vampi")
    rig.add_run(OTHER, "clinica-piloto")

    written = rig.indexer().rebuild()

    assert written == ("index.html", "history-clinica-piloto.html", "history-vampi.html")
    index = rig.index_files.written["index.html"]
    assert "2 produtos testados · 3 testes feitos" in index
    assert f'href="{NEW}/panel/summary.html"' in index
    history = rig.index_files.written["history-vampi.html"]
    assert history.count("<tr") == 3


def test_the_letter_comes_from_the_profile_and_is_unknown_without_one() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    rig.add_run(OTHER, "clinica-piloto")

    rig.indexer().rebuild()

    index = rig.index_files.written["index.html"]
    assert "Carta CHG-4821 válida até 31/12/2999" in index
    assert "Carta não consultada" in index


def test_a_corrupted_run_becomes_a_no_data_row_and_the_others_survive() -> None:
    rig = Rig()
    rig.add_run(OLD, "vampi")
    rig.add_run(NEW, "vampi")
    rig.files.broken.add(OLD)

    rig.indexer().rebuild()

    history = rig.index_files.written["history-vampi.html"]
    assert "sem dados" in history
    assert history.count("<tr") == 3
    assert "Varredura completa" in history


def test_a_run_with_one_unreadable_file_is_kept_with_an_incomplete_data_notice() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    rig.files.unreadable.add("metrics.json")

    rig.indexer().rebuild()

    assert "dados incompletos" in rig.index_files.written["history-vampi.html"]


def test_a_folder_without_any_known_file_is_a_no_data_row_too() -> None:
    rig = Rig()
    rig.index_files.add(NEW, "vampi")

    rig.indexer().rebuild()

    assert "sem dados" in rig.index_files.written["history-vampi.html"]


def test_the_date_of_a_no_data_row_comes_from_the_folder_stamp() -> None:
    rig = Rig()
    rig.index_files.add(NEW, "vampi")

    rig.indexer().rebuild()

    assert "13/11 · 20:08" in rig.index_files.written["history-vampi.html"]


def test_a_write_failure_is_a_config_error() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    rig.index_files.write_error = ConfigError("Não foi possível gravar os índices do painel.")

    with pytest.raises(ConfigError):
        rig.indexer().rebuild()


# ------------------------------------------------------------ envoltório


class FakePanel:
    def __init__(self, entry: str | None = "panel/summary.html") -> None:
        self.entry = entry
        self.calls: list[str] = []
        self.error: ConfigError | None = None

    def execute(self, request: PanelRequest) -> PanelOutcome:
        self.calls.append("execute")
        if self.error is not None:
            raise self.error
        return PanelOutcome(
            product=request.product,
            run_id=NEW,
            directory="panel",
            entry="panel/summary.html",
            files=("panel/summary.html",),
            verdict="finished",
            severe_findings=0,
            sources=(),
            missing=(),
        )

    def refresh(self, product: str, run_id: str) -> str | None:
        self.calls.append("refresh")
        return self.entry


def test_generating_a_test_panel_rebuilds_the_indexes_after_it() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    panel = FakePanel()

    result = IndexedPanel(panel, rig.indexer()).execute(PanelRequest(product="vampi"))

    assert panel.calls == ["execute"]
    assert result.panel is not None
    assert result.indexes == ("index.html", "history-vampi.html")


def test_the_index_only_mode_does_not_touch_any_test_panel() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    panel = FakePanel()

    result = IndexedPanel(panel, rig.indexer()).rebuild_indexes()

    assert panel.calls == []
    assert result.panel is None
    assert "index.html" in result.indexes


def test_a_panel_that_fails_does_not_write_the_indexes() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    panel = FakePanel()
    panel.error = ConfigError("Não há nenhuma execução deste produto.")

    with pytest.raises(ConfigError):
        IndexedPanel(panel, rig.indexer()).execute(PanelRequest(product="vampi"))

    assert rig.index_files.written == {}


def test_refresh_never_raises_even_if_the_indexes_cannot_be_written() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi")
    rig.index_files.write_error = ConfigError("disco cheio")
    panel = FakePanel()

    entry = IndexedPanel(panel, rig.indexer()).refresh("vampi", NEW)

    assert entry == "panel/summary.html"
    assert panel.calls == ["refresh"]


def test_refresh_still_rebuilds_the_indexes_when_the_panel_was_not_written() -> None:
    rig = Rig()
    rig.add_run(NEW, "vampi", panel=False)

    entry = IndexedPanel(FakePanel(entry=None), rig.indexer()).refresh("vampi", NEW)

    assert entry is None
    assert "sem painel" in rig.index_files.written["history-vampi.html"]


def test_the_folder_the_preflight_of_a_run_opened_for_itself_is_not_listed_as_a_test() -> None:
    rig = Rig()
    orphan = "2026-11-13T20-07-00Z-vampi-0f0f"
    rig.add_run(NEW, "vampi")
    stages = list(run_summary().stages)
    stages[0] = stages[0].model_copy(update={"run_id": orphan})
    rig.files.summary[NEW] = run_summary(run_id=NEW, stages=tuple(stages))
    rig.index_files.add(orphan, "vampi")

    rig.indexer().rebuild()

    history = rig.index_files.written["history-vampi.html"]
    assert history.count("<tr") == 2
    assert "1 teste feito" in rig.index_files.written["index.html"]


def test_a_preflight_folder_that_no_run_cites_stays_listed_as_a_conference_only_test() -> None:
    rig = Rig()
    alone = "2026-11-13T20-07-00Z-vampi-0f0f"
    rig.add_run(NEW, "vampi")
    rig.index_files.add(alone, "vampi")

    rig.indexer().rebuild()

    assert rig.index_files.written["history-vampi.html"].count("<tr") == 3
