"""O `report` sobre alertas e evidência CAPTURADOS do ZAP 2.17 real (VAmPI vulnerável)."""

import shutil
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.sinks import JsonFindingsSink, MarkdownReportSink
from harness_dast.application.report import Report, ReportOutcome, ReportRequest
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository

REAL = Path(__file__).parents[2] / "fixtures" / "zap_real"
RUN_ID = "2026-11-13T08-46-09Z-vampi-b1d4"


def build(tmp_path: Path) -> ReportOutcome:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    for name in ("probe.json", "scan.json", "alerts.raw.json", "evidence.json"):
        shutil.copy(REAL / name, directory / name)
    profiles = InMemoryProfileRepository()
    profiles.add(valid_profile("vampi"))
    return Report(
        profiles=profiles,
        artifacts=FileRunArtifacts(tmp_path),
        sinks=[JsonFindingsSink(tmp_path), MarkdownReportSink(tmp_path)],
        clock=FixedClock(utc(2026, 11, 13, 9)),
        harness_version="0.0-real",
    ).execute(ReportRequest(product="vampi", run_id=RUN_ID, fail_on="high"))


def test_real_alerts_become_findings_with_the_sql_injection_as_high(tmp_path: Path) -> None:
    outcome = build(tmp_path)

    report = outcome.report
    assert report.summary.alerts_unreadable == 0
    sqli = [f for f in report.findings if f.title == "SQL Injection"]
    assert sqli
    assert {f.proposed_severity for f in sqli} == {"high"}
    assert all(f.classification.cwe == 89 for f in sqli)
    assert outcome.exceeds_threshold is True


def test_every_real_alert_is_attributed_through_its_source_message(tmp_path: Path) -> None:
    report = build(tmp_path).report

    assert {f.attribution for f in report.findings} == {"source_message"}


def test_real_capture_keeps_secrets_out_of_findings_and_markdown(tmp_path: Path) -> None:
    build(tmp_path)
    directory = tmp_path / RUN_ID

    produced = (directory / "findings.json").read_text("utf-8") + (
        directory / "report.md"
    ).read_text("utf-8")

    assert "eyJ" not in produced
    assert "Authorization: ***" in produced
