"""`retest.json` no armazém de artefatos: ida e volta com arquivo atômico e conteúdo versionado."""

import json
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.retest import RetestReport, build_retest_report
from harness_dast.domain.run_summary import RunOptions, RunSummary
from tests.fakes.verification_data import finding
from tests.unit.domain.report.helpers import RUN_ID


def _report() -> RetestReport:
    item = finding().model_copy(update={"operation_id": "getPet"})
    return build_retest_report(
        product="demo",
        previous_run_id="2026-11-12T10-00-00Z-demo-0001",
        run_id=RUN_ID,
        generated_at="2026-11-13T10:00:00+00:00",
        selected=[item],
        current=[],
        scanned_operations={"getPet"},
    )


def test_write_retest_saves_a_versioned_file_that_reads_back(tmp_path: Path) -> None:
    store = FileRunArtifacts(tmp_path)

    name = store.write_retest(RUN_ID, _report())

    saved = json.loads((tmp_path / RUN_ID / name).read_text(encoding="utf-8"))
    assert name == "retest.json"
    assert saved["schema_version"] == 1
    assert RetestReport.model_validate(saved) == _report()
    assert sorted(p.name for p in (tmp_path / RUN_ID).iterdir()) == ["retest.json"]


def test_write_retest_lists_the_file_in_run_json_atomically(tmp_path: Path) -> None:
    store = FileRunArtifacts(tmp_path)
    store.write_summary(RUN_ID, _summary())

    store.write_retest(RUN_ID, _report())

    saved = store.read_summary(RUN_ID)
    assert saved is not None
    assert saved.artifacts["retest.json"] == "retest.json"
    assert "run.json" not in {p.name for p in (tmp_path / RUN_ID).glob(".*.tmp")}
    assert sorted(p.name for p in (tmp_path / RUN_ID).iterdir()) == ["retest.json", "run.json"]


def _summary() -> RunSummary:
    return RunSummary(
        product="demo",
        run_id=RUN_ID,
        status="completed",
        exit_code=0,
        started_at="2026-11-13T10:00:00+00:00",
        finished_at="2026-11-13T10:05:00+00:00",
        duration_seconds=300.0,
        options=RunOptions(),
        stages=(),
        artifacts={},
    )
