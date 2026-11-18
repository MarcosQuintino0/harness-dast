"""`retest.json` no armazém de artefatos: ida e volta com arquivo atômico e conteúdo versionado."""

import json
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.domain.retest import RetestReport, build_retest_report
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
