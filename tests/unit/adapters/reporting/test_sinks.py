"""Destinos do relatório: arquivos atômicos, UTF-8, e o JSON é o contrato público."""

import json
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.sinks import JsonFindingsSink, MarkdownReportSink
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_model import FindingsReport
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report_helpers import RUN_ID, entry, operation, probe_result, scan_result


def make_report() -> FindingsReport:
    ops = [operation("obter", "GET", "/users/v1/{username}")]
    return assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4)]),
        raw_alerts=[zap_alert("9")],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=None,
        csrf_header=None,
    )


def test_json_sink_writes_a_findings_file_that_the_store_reads_back(tmp_path: Path) -> None:
    report = make_report()

    name = JsonFindingsSink(tmp_path).write(RUN_ID, report)

    assert name == "findings.json"
    assert FileRunArtifacts(tmp_path).read_findings(RUN_ID) == report
    data = json.loads((tmp_path / RUN_ID / "findings.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["fingerprint_version"] == 1
    assert data["findings"][0]["status"] == "needs_triage"
    assert list(data["findings"][0]).count("fingerprint") == 1


def test_markdown_sink_writes_utf_8_with_unix_newlines(tmp_path: Path) -> None:
    name = MarkdownReportSink(tmp_path).write(RUN_ID, make_report())

    raw = (tmp_path / RUN_ID / name).read_bytes()
    assert name == "report.md"
    assert b"\r\n" not in raw
    assert "Relatório de varredura".encode() in raw
    assert sorted(p.name for p in (tmp_path / RUN_ID).iterdir()) == ["report.md"]


@pytest.mark.parametrize("sink", [JsonFindingsSink, MarkdownReportSink])
def test_sinks_validate_the_run_id_and_report_write_failures(sink: type, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="inválido"):
        sink(tmp_path).write("../fora", make_report())

    blocked = tmp_path / "ocupado"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="Não foi possível gravar"):
        sink(blocked).write(RUN_ID, make_report())
