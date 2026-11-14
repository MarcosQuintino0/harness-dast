"""`report` e `run` chamam o painel por último e nunca caem por causa dele (ADR 0032)."""

from tests.fakes.rig import agenda_flows
from tests.fakes.scan_rig import ScanRig
from tests.unit.application.test_run import RUN_ID, Rig


class RecordingPanel:
    """`PanelRefresher` falso: guarda o pedido e devolve a página de entrada, ou `None`."""

    def __init__(self, entry: str | None = "panel/summary.html") -> None:
        self.entry = entry
        self.calls: list[tuple[str, str]] = []

    def refresh(self, product: str, run_id: str) -> str | None:
        self.calls.append((product, run_id))
        return self.entry


def scanned() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    rig.run_scan()
    return rig


def report_with(rig: ScanRig, panel: RecordingPanel | None) -> object:
    from harness_dast.application.report import Report, ReportRequest

    use_case = Report(
        profiles=rig.profiles,
        artifacts=rig.artifacts,
        sinks=[rig.sink],
        clock=rig.clock,
        harness_version="0.0-test",
        metrics=rig.metrics_recorder(),
        panel=panel,
    )
    return use_case.execute(ReportRequest(product="agenda", run_id=rig.probe_result.run_id))


def test_report_asks_for_the_panel_after_the_reports_and_the_metrics() -> None:
    rig = scanned()
    panel = RecordingPanel()

    outcome = report_with(rig, panel)

    assert panel.calls == [("agenda", rig.probe_result.run_id)]
    assert outcome.panel_file == "panel/summary.html"  # type: ignore[attr-defined]
    assert outcome.metrics_file == "metrics.json"  # type: ignore[attr-defined]


def test_report_without_a_panel_has_no_panel_file() -> None:
    outcome = report_with(scanned(), None)

    assert outcome.panel_file is None  # type: ignore[attr-defined]


def test_a_panel_that_could_not_be_written_does_not_change_the_report_result() -> None:
    rig = scanned()

    outcome = report_with(rig, RecordingPanel(entry=None))

    assert outcome.panel_file is None  # type: ignore[attr-defined]
    assert outcome.files == ("list.json",)  # type: ignore[attr-defined]
    assert outcome.report.findings is not None  # type: ignore[attr-defined]


def test_run_refreshes_the_panel_once_at_the_end_after_run_json_is_written() -> None:
    panel = RecordingPanel()
    rig = Rig(panel=panel)

    result = rig.run()

    assert panel.calls == [("demo", RUN_ID)]
    assert RUN_ID in rig.sink.summaries
    assert result.error is None


def test_run_refreshes_the_panel_even_when_a_stage_fails() -> None:
    panel = RecordingPanel()
    from tests.unit.application.test_run import _scan

    rig = Rig(panel=panel, scan=lambda: _scan("stopped_zap"))

    result = rig.run()

    assert result.error is not None
    assert panel.calls == [("demo", RUN_ID)]


def test_run_without_a_panel_still_writes_run_json() -> None:
    rig = Rig()

    rig.run()

    assert RUN_ID in rig.sink.summaries


def test_run_refreshes_the_panel_of_the_preflight_folder_when_the_preflight_fails() -> None:
    from tests.unit.application.test_run import _preflight

    panel = RecordingPanel()
    rig = Rig(panel=panel, preflight=lambda: _preflight(ready=False))

    result = rig.run()

    assert result.error is not None
    assert panel.calls == [("demo", "pre-run")]
