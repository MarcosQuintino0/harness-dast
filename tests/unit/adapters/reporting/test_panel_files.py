"""Arquivos do painel em disco: leitura opcional, execução mais recente e escrita só em `panel/`."""

from pathlib import Path

import pytest

from harness_dast.adapters.reporting.panel_files import FilePanelFiles
from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_metrics import RunMetrics, build_run_metrics
from tests.unit.domain.panel.helpers import findings_report, run_summary
from tests.unit.domain.report.helpers import RUN_ID, entry, operation, probe_result, scan_result


@pytest.fixture
def files(tmp_path: Path) -> FilePanelFiles:
    return FilePanelFiles(tmp_path)


def test_every_read_is_none_when_the_file_does_not_exist(files: FilePanelFiles) -> None:
    assert files.read_summary(RUN_ID) is None
    assert files.read_metrics(RUN_ID) is None
    assert files.read_manifest(RUN_ID) is None
    assert files.read_probe(RUN_ID) is None
    assert files.read_scan(RUN_ID) is None
    assert files.read_findings(RUN_ID) is None
    assert files.read_authz(RUN_ID) is None


def test_reads_return_what_the_other_stages_wrote(tmp_path: Path, files: FilePanelFiles) -> None:
    store = FileRunArtifacts(tmp_path)
    scan = scan_result([entry("obter", "GET", "/u/{id}", 4)])
    store.write_scan(RUN_ID, scan)
    store.write_summary(RUN_ID, run_summary())
    store.write_metrics(RUN_ID, _metrics())
    folder = tmp_path / RUN_ID
    (folder / "probe.json").write_text(
        probe_result([operation("obter", "GET", "/u/{id}")]).model_dump_json(), encoding="utf-8"
    )
    (folder / "findings.json").write_text(findings_report().model_dump_json(), encoding="utf-8")

    assert files.read_scan(RUN_ID) == scan
    assert files.read_summary(RUN_ID) == run_summary()
    assert files.read_metrics(RUN_ID) is not None
    assert files.read_probe(RUN_ID) is not None
    assert files.read_findings(RUN_ID) == findings_report()


def _metrics() -> RunMetrics:
    manifest = RunManifest(
        run_id=RUN_ID,
        command="probe",
        product="vampi",
        harness_version="1",
        hashes=ArtifactHashes(),
        limits=RunLimits(requests_per_second=1, max_duration_minutes=1, zap_threads_per_host=1),
        seed=1,
        started_at="2026-11-13T05:15:32+00:00",
    )
    return build_run_metrics(
        manifest=manifest, probe=None, scan=None, authz=None, rule_stats=None, proxy_rows=None,
        stages=None, run_window=None, report_seconds=None, path_mode="strict",
        harness_version="1", generated_at="2026-11-13T06:00:00+00:00",
    )  # fmt: skip


@pytest.mark.parametrize("name", ["run.json", "scan.json", "findings.json", "metrics.json"])
def test_a_corrupt_file_is_a_config_error_with_what_to_redo(
    tmp_path: Path, files: FilePanelFiles, name: str
) -> None:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    (folder / name).write_text("{ não é json", encoding="utf-8")
    reader = {
        "run.json": files.read_summary,
        "scan.json": files.read_scan,
        "findings.json": files.read_findings,
        "metrics.json": files.read_metrics,
    }[name]

    with pytest.raises(ConfigError, match="ilegível"):
        reader(RUN_ID)


def test_a_file_with_the_wrong_shape_is_a_config_error(
    tmp_path: Path, files: FilePanelFiles
) -> None:
    folder = tmp_path / RUN_ID
    folder.mkdir()
    (folder / "run.json").write_text('{"product": 1}', encoding="utf-8")

    with pytest.raises(ConfigError):
        files.read_summary(RUN_ID)


def test_reading_with_an_invalid_run_id_is_refused(files: FilePanelFiles) -> None:
    with pytest.raises(ConfigError):
        files.read_scan("../../etc")


def test_latest_run_id_picks_the_newest_folder_of_the_product(
    tmp_path: Path, files: FilePanelFiles
) -> None:
    for name in (
        "2026-11-12T05-15-32Z-vampi-ab12",
        "2026-11-14T02-14-18Z-vampi-f087",
        "2026-11-15T00-00-00Z-outro-aaaa",
        "2026-11-13T05-15-32Z-vampi-cd34",
        "nao-e-uma-execucao",
    ):
        (tmp_path / name).mkdir()
    (tmp_path / "2026-11-16T00-00-00Z-vampi-eeee").write_text(
        "arquivo, não pasta", encoding="utf-8"
    )

    assert files.latest_run_id("vampi") == "2026-11-14T02-14-18Z-vampi-f087"
    assert files.latest_run_id("outro") == "2026-11-15T00-00-00Z-outro-aaaa"
    assert files.latest_run_id("sem-execucao") is None


def test_latest_run_id_does_not_confuse_a_product_with_a_longer_name(
    tmp_path: Path, files: FilePanelFiles
) -> None:
    (tmp_path / "2026-11-14T02-14-18Z-clinica-piloto-f087").mkdir()

    assert files.latest_run_id("clinica") is None
    assert files.latest_run_id("piloto") is None
    assert files.latest_run_id("clinica-piloto") == "2026-11-14T02-14-18Z-clinica-piloto-f087"


def test_latest_run_id_is_none_when_the_runs_folder_does_not_exist(tmp_path: Path) -> None:
    assert FilePanelFiles(tmp_path / "nao-existe").latest_run_id("vampi") is None


def test_write_pages_puts_each_page_inside_the_panel_folder_and_leaves_no_temporary(
    tmp_path: Path, files: FilePanelFiles
) -> None:
    written = files.write_pages(RUN_ID, {"summary.html": "<p>á</p>", "stages.html": "<p>b</p>"})

    assert written == ("panel/summary.html", "panel/stages.html")
    folder = tmp_path / RUN_ID / "panel"
    assert (folder / "summary.html").read_text(encoding="utf-8") == "<p>á</p>"
    assert sorted(item.name for item in folder.iterdir()) == ["stages.html", "summary.html"]


def test_write_pages_replaces_the_previous_version(tmp_path: Path, files: FilePanelFiles) -> None:
    files.write_pages(RUN_ID, {"summary.html": "um"})
    files.write_pages(RUN_ID, {"summary.html": "dois"})

    assert (tmp_path / RUN_ID / "panel" / "summary.html").read_text(encoding="utf-8") == "dois"


@pytest.mark.parametrize(
    "name",
    ["../summary.html", "a/b.html", "..\\x.html", "SUMMARY.html", "x.js", "", ".hidden.html"],
)
def test_write_pages_refuses_a_page_name_that_could_leave_the_folder(
    tmp_path: Path, files: FilePanelFiles, name: str
) -> None:
    with pytest.raises(ConfigError, match="Nome de página"):
        files.write_pages(RUN_ID, {name: "x"})

    assert not (tmp_path / "summary.html").exists()


def test_write_pages_refuses_an_invalid_run_id(files: FilePanelFiles) -> None:
    with pytest.raises(ConfigError):
        files.write_pages("../fora", {"summary.html": "x"})


def test_write_pages_failure_is_a_config_error_with_a_hint(tmp_path: Path) -> None:
    blocker = tmp_path / RUN_ID
    blocker.write_text("é um arquivo, não uma pasta", encoding="utf-8")

    with pytest.raises(ConfigError, match="gravar") as caught:
        FilePanelFiles(tmp_path).write_pages(RUN_ID, {"summary.html": "x"})

    assert caught.value.hint is not None
