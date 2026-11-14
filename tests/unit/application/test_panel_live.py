"""Página ao vivo: regravada a cada etapa e função, com recarga só durante, sem derrubar o `run`."""

from datetime import UTC, datetime

from harness_dast.application.panel_index import PanelIndexer
from harness_dast.application.panel_live import LiveBoard
from harness_dast.application.preflight_report import PreflightReport
from harness_dast.application.scan import ScanRequest
from harness_dast.domain.api_model import Operation
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run_summary import StageRecord
from tests.fakes.panel_index_ports import BreakableFiles, FakeIndexFiles, RecordingLive
from tests.fakes.panel_ports import FakeSpecLoader
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_rig import ScanRig
from tests.unit.application.test_run import RUN_ID, Kill, Rig, _outcome, _scan
from tests.unit.domain.panel_helpers import XSS, sources

OPERATIONS = (
    Operation(operation_id="cadastrar", method="post", path="/p", summary="Cadastrar paciente"),
    Operation(operation_id="hostil", method="get", path="/h", summary=XSS),
)


class Setup:
    """Placa de teste: a página ao vivo real sobre arquivos e relógio falsos."""

    def __init__(self, *, indexer: PanelIndexer | None = None) -> None:
        self.rig = Rig(
            preflight=lambda: PreflightReport(product="demo", ready=True, checks=(), run_id=RUN_ID)
        )
        self.files = BreakableFiles()
        self.files.probe[RUN_ID] = sources().probe  # type: ignore[assignment]
        profiles = InMemoryProfileRepository()
        profiles.add(valid_profile("demo"))
        self.kill: Kill = self.rig.kill
        self.board = LiveBoard(
            files=self.files,
            profiles=profiles,
            specs=FakeSpecLoader(OPERATIONS),
            clock=self.rig.clock,
            timezone=UTC,
            kill_switch=self.kill,
            indexer=indexer,
        )
        self.rig.live = self.board

    def pages(self) -> list[str]:
        return self.files.live_pages(RUN_ID)


def test_the_run_rewrites_the_page_on_each_stage_change_and_once_more_at_the_end() -> None:
    setup = Setup()

    result = setup.rig.run()

    pages = setup.pages()
    assert result.error is None
    assert len(pages) == 4
    assert "Alcance · agora" in pages[0]
    assert "Varredura · agora" in pages[1]
    assert "Achados · agora" in pages[2]


def test_the_page_reloads_during_the_run_and_not_after_it() -> None:
    setup = Setup()

    setup.rig.run()

    pages = setup.pages()
    assert all('http-equiv="refresh"' in page for page in pages[:-1])
    assert 'http-equiv="refresh"' not in pages[-1]
    assert "O teste terminou." in pages[-1]
    assert 'href="stages.html"' in pages[-1]


def test_the_run_without_a_run_folder_writes_no_page() -> None:
    setup = Setup()
    setup.rig.preflight = lambda: PreflightReport(
        product="demo", ready=False, checks=(), run_id="pre-run"
    )

    setup.rig.run()

    assert setup.files.history == []


def test_a_write_error_never_changes_the_result_of_the_run() -> None:
    setup = Setup()
    setup.files.write_error = ConfigError("disco cheio")

    result = setup.rig.run()

    assert result.error is None
    assert result.summary.exit_code == 0
    assert result.summary.status == "completed"
    assert RUN_ID in setup.rig.sink.summaries


def test_a_run_that_fails_ends_the_page_as_stopped_with_the_reason() -> None:
    setup = Setup()
    setup.rig.scan = lambda: _scan("stopped_zap", "O ZAP caiu.")

    result = setup.rig.run()

    last = setup.pages()[-1]
    assert result.error is not None
    assert 'http-equiv="refresh"' not in last
    assert "O teste parou no meio." in last
    assert "O ZAP caiu." in last


def test_each_function_of_the_scan_rewrites_the_page_with_the_count_and_the_simple_name() -> None:
    setup = Setup()
    setup.board.stage_started(
        "demo", RUN_ID, "scan", (), started=datetime(2026, 11, 13, 10, tzinfo=UTC), authz=False
    )

    setup.board.scan_progress(RUN_ID, 0, 2, "cadastrar", None)
    setup.board.scan_progress(RUN_ID, 1, 2, "hostil", None)

    pages = setup.pages()
    assert len(pages) == 3
    assert "Função 1 de 2" in pages[1]
    assert "Cadastrar paciente" in pages[1]
    assert "Função 2 de 2" in pages[2]
    assert "<script" not in pages[2]
    assert "&lt;script&gt;" in pages[2]


def test_the_page_reads_the_probe_for_the_reached_functions_once_the_scan_starts() -> None:
    setup = Setup()

    setup.board.stage_started(
        "demo", RUN_ID, "scan", (), started=datetime(2026, 11, 13, 10, tzinfo=UTC), authz=False
    )

    probe = sources().probe
    assert probe is not None
    expected = f"{probe.summary.successes} de {probe.summary.operations_sent}"
    assert expected in setup.pages()[0]


def test_progress_before_any_stage_or_for_another_run_is_ignored() -> None:
    setup = Setup()

    setup.board.scan_progress(RUN_ID, 0, 2, "cadastrar", None)
    setup.board.stage_started(
        "demo", RUN_ID, "scan", (), started=datetime(2026, 11, 13, 10, tzinfo=UTC), authz=False
    )
    setup.board.scan_progress("outra-execucao", 0, 2, "cadastrar", None)

    assert len(setup.pages()) == 1


def test_with_the_kill_switch_engaged_the_page_says_stopping() -> None:
    setup = Setup()
    setup.kill.on = True

    setup.board.stage_started(
        "demo", RUN_ID, "scan", (), started=datetime(2026, 11, 13, 10, tzinfo=UTC), authz=False
    )

    assert "O teste está parando." in setup.pages()[0]


def test_authz_appears_in_the_track_only_when_it_was_asked_for() -> None:
    setup = Setup()
    started = datetime(2026, 11, 13, 10, tzinfo=UTC)
    records = (StageRecord(name="preflight", status="ok", duration_seconds=3.0),)

    setup.board.stage_started("demo", RUN_ID, "probe", records, started=started, authz=True)
    with_authz = setup.pages()[-1]
    other = Setup()
    other.board.stage_started("demo", RUN_ID, "probe", records, started=started, authz=False)

    assert "Entre contas" in with_authz
    assert "Entre contas" not in other.pages()[-1]


def test_the_first_write_rebuilds_the_indexes_once_and_links_the_path() -> None:
    index_files = FakeIndexFiles()
    indexer = PanelIndexer(
        files=BreakableFiles(),
        index_files=index_files,
        profiles=InMemoryProfileRepository(),
        clock=Rig().clock,
        timezone=UTC,
    )
    setup = Setup(indexer=indexer)

    setup.rig.run()

    assert "index.html" in index_files.written
    assert 'href="../../index.html">hdast</a>' in setup.pages()[0]


def test_if_the_indexes_cannot_be_written_the_path_is_text_and_the_run_goes_on() -> None:
    index_files = FakeIndexFiles()
    index_files.write_error = ConfigError("sem permissão")
    indexer = PanelIndexer(
        files=BreakableFiles(),
        index_files=index_files,
        profiles=InMemoryProfileRepository(),
        clock=Rig().clock,
        timezone=UTC,
    )
    setup = Setup(indexer=indexer)

    result = setup.rig.run()

    assert result.error is None
    assert '<span class="crumb">hdast</span>' in setup.pages()[0]
    assert "../../index.html" not in setup.pages()[0]


def test_the_run_announces_each_stage_and_the_end_to_the_live_port() -> None:
    live = RecordingLive()
    rig = Rig(
        live=live,
        preflight=lambda: PreflightReport(product="demo", ready=True, checks=(), run_id=RUN_ID),
        report=_outcome,
    )

    rig.run()

    assert live.stages == ["probe", "scan", "report"]
    assert len(live.finished) == 1
    assert live.finished[0].run_id == RUN_ID


def test_the_scan_announces_each_function_and_the_end() -> None:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    live = RecordingLive()

    result = rig.scan(live).execute(ScanRequest(product="agenda", run_id=rig.probe_result.run_id))

    total = len(result.entries)
    assert total >= 1
    assert [done for done, _, _ in live.progress] == list(range(total + 1))
    assert live.progress[0][2] is not None
    assert live.progress[-1] == (total, total, None)
