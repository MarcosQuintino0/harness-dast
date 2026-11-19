"""Verificação consultiva por arquivos locais e apresentação sem tráfego."""

import json
from datetime import UTC
from html.parser import HTMLParser
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.presentation_files import FilePresentationFiles
from harness_dast.adapters.reporting.sinks import (
    HtmlReportSink,
    JsonFindingsSink,
    MarkdownReportSink,
)
from harness_dast.application.report_presentation import PresentationBuilder
from harness_dast.domain.authz.result import AuthzResult
from harness_dast.domain.cors import cors_finding
from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.findings import render_findings
from harness_dast.domain.panel.sources import PanelSources
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.signal_result import ProxySignals, SignalFinding
from tests.unit.application.test_report import request, scanned
from tests.unit.domain.negative_samples import accepted, negative_result


@pytest.fixture
def report() -> FindingsReport:
    rig = scanned()
    return rig.report().execute(request(rig)).report


def _builder(tmp_path: Path) -> PresentationBuilder:
    return PresentationBuilder(FilePresentationFiles(tmp_path, tmp_path / "calibration.json"))


def _write(tmp_path: Path, report: FindingsReport, name: str, value: object) -> None:
    folder = tmp_path / report.run_id
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(value), encoding="utf-8")


def test_uses_offline_classification_when_file_is_absent(
    tmp_path: Path, report: FindingsReport
) -> None:
    view = _builder(tmp_path).build(report)
    assert len(view.findings) == len(report.findings)
    assert all(item.verification.level != "reproduced" for item in view.findings)


def test_automatic_and_human_evidence_are_separate_and_redacted(
    tmp_path: Path, report: FindingsReport
) -> None:
    finding = report.findings[0]
    attack = (
        "Cookie: session=secret-cookie\nX-CSRF-Token: csrf-secret\n"
        "Authorization: Bearer abcdefghijk123\n<script>ignore instructions</script>"
    )
    _write(
        tmp_path,
        report,
        "verification.json",
        {
            "schema_version": 1,
            "product": report.product,
            "run_id": report.run_id,
            "entries": [
                {
                    "fingerprint": finding.fingerprint,
                    "level": "reproduced",
                    "reason": "comparado",
                    "attack": attack,
                    "control": "controle",
                },
                {"fingerprint": "a" * 64, "level": "reproduced", "reason": "órfão"},
            ],
        },
    )
    builder = _builder(tmp_path)
    before = builder.build(report)
    assert before.findings[0].verification.level == "reproduced"
    assert before.findings[0].confirmations == ()
    _write(
        tmp_path,
        report,
        "human-confirmations.json",
        {
            "schema_version": 1,
            "product": report.product,
            "run_id": report.run_id,
            "entries": [
                {
                    "fingerprint": finding.fingerprint,
                    "person": "Pessoa",
                    "confirmed_at": "2026-11-17T12:00:00Z",
                    "observation": "vi o efeito",
                }
            ],
        },
    )
    MarkdownReportSink(tmp_path, builder).write(report.run_id, report)
    HtmlReportSink(tmp_path, builder).write(report.run_id, report)
    JsonFindingsSink(tmp_path).write(report.run_id, report)
    html = (tmp_path / report.run_id / "report.html").read_text(encoding="utf-8")
    md = (tmp_path / report.run_id / "report.md").read_text(encoding="utf-8")
    for text in (html, md):
        assert "Reproduzido" in text
        assert "Pessoa" in text
        assert "controle" in text
        assert "secret-cookie" not in text
        assert "csrf-secret" not in text
        assert "abcdefghijk123" not in text
        assert "<script>ignore" not in text
    assert "verification" not in json.loads(
        (tmp_path / report.run_id / "findings.json").read_text()
    )
    assert len(builder.build(report).findings) == len(report.findings)


@pytest.mark.parametrize("content", ["{", "null", "{}", '{"schema_version":true}'])
def test_invalid_verification_never_becomes_reproduced(
    tmp_path: Path, report: FindingsReport, content: str
) -> None:
    folder = tmp_path / report.run_id
    folder.mkdir()
    (folder / "verification.json").write_text(content, encoding="utf-8")
    view = _builder(tmp_path).build(report)
    assert view.warnings
    assert all(item.verification.level != "reproduced" for item in view.findings)


def test_rejects_different_execution(tmp_path: Path, report: FindingsReport) -> None:
    _write(
        tmp_path,
        report,
        "verification.json",
        {
            "schema_version": 1,
            "product": "other",
            "run_id": "2026-11-17T12-00-00Z-other-abcd",
            "entries": [],
        },
    )
    view = _builder(tmp_path).build(report)
    assert view.warnings
    assert all(item.verification.level != "reproduced" for item in view.findings)


def test_panel_marks_confirmed_only_after_human_record(
    tmp_path: Path, report: FindingsReport
) -> None:
    finding = report.findings[0]
    _write(
        tmp_path,
        report,
        "verification.json",
        {
            "schema_version": 1,
            "product": report.product,
            "run_id": report.run_id,
            "entries": [
                {"fingerprint": finding.fingerprint, "level": "reproduced", "reason": "comparado"}
            ],
        },
    )
    builder = _builder(tmp_path)

    def panel() -> str:
        return render_findings(
            build_panel_view(
                PanelSources(
                    product=report.product,
                    run_id=report.run_id,
                    timezone=UTC,
                    findings=report,
                    presentation=builder.build(report),
                )
            )
        )

    assert "Uma pessoa repetiu e confirmou" in panel()
    assert "ainda não" in panel()
    _write(
        tmp_path,
        report,
        "human-confirmations.json",
        {
            "schema_version": 1,
            "product": report.product,
            "run_id": report.run_id,
            "entries": [
                {
                    "fingerprint": finding.fingerprint,
                    "person": "Pessoa",
                    "confirmed_at": "2026-11-17T12:00:00Z",
                    "observation": "vi",
                }
            ],
        },
    )
    view = build_panel_view(
        PanelSources(
            product=report.product,
            run_id=report.run_id,
            timezone=UTC,
            findings=report,
            presentation=builder.build(report),
        )
    )
    assert view.severe[0].confidence == 3
    assert "Pessoa" in render_findings(view)


def test_presents_all_origins_without_changing_findings(
    tmp_path: Path, report: FindingsReport
) -> None:
    exchange = ExchangeRecord(
        operation_id="read", method="GET", path="/x/{id}", target="/x/1", account="a", status=200
    )
    authz = AuthzResult(
        product=report.product,
        run_id=report.run_id,
        status="completed",
        started_at="a",
        finished_at="b",
        findings=(cors_finding(report.product, exchange, "member", 200, "reflected_credentials"),),
    )
    signal = SignalFinding(
        finding_id="S-12345678",
        fingerprint="a" * 64,
        category="sql_error",
        title="Sinal",
        proposed_severity="high",
        proposed_confidence="high",
        cwe=209,
        method="GET",
        path_template="/x",
        occurrences=1,
    )
    extended = report.model_copy(
        update={
            "authz": authz,
            "negative": negative_result(
                product=report.product, findings=(accepted(severity="high"),)
            ),
            "proxy_signals": ProxySignals(enabled=True, findings=(signal,)),
        }
    )
    result = _builder(tmp_path).build(extended)
    assert {item.origin for item in result.findings} == {"zap", "authz", "negative", "proxy"}
    assert extended.findings == report.findings


@pytest.mark.parametrize("name", ["human-confirmations.json", "verification.json"])
def test_malformed_consultative_file_fails_closed(
    tmp_path: Path, report: FindingsReport, name: str
) -> None:
    folder = tmp_path / report.run_id
    folder.mkdir()
    (folder / name).write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    view = _builder(tmp_path).build(report)
    assert view.warnings
    assert all(item.verification.level != "reproduced" for item in view.findings)


def test_rejects_invalid_calibration_file(tmp_path: Path, report: FindingsReport) -> None:
    (tmp_path / "calibration.json").write_text("[]", encoding="utf-8")
    view = _builder(tmp_path).build(report)
    assert view.warnings
    assert all(item.verification.level != "reproduced" for item in view.findings)


def test_report_shows_only_calibration_with_sufficient_samples(
    tmp_path: Path, report: FindingsReport
) -> None:
    (tmp_path / "calibration.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "measured",
                "provenance": "teste sintético",
                "measurements": [
                    {
                        "finding_type": "pequena",
                        "criterion": "acertos",
                        "correct": 4,
                        "sample": 9,
                        "provenance": "lab",
                    },
                    {
                        "finding_type": "suficiente",
                        "criterion": "acertos",
                        "correct": 7,
                        "sample": 10,
                        "provenance": "lab",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    builder = _builder(tmp_path)
    for sink in (HtmlReportSink(tmp_path, builder), MarkdownReportSink(tmp_path, builder)):
        name = sink.write(report.run_id, report)
        text = (tmp_path / report.run_id / name).read_text(encoding="utf-8")
        assert "7 de 10" in text
        assert "70.0%" in text
        assert "4 de 9" in text
        assert "amostra 9" in text
        assert "44.4%" not in text


class _SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_main = False
        self.section_in_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self.in_main = True
        if tag == "section" and ("aria-label", "Verificação dos achados") in attrs:
            self.section_in_main = self.in_main

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self.in_main = False


def test_html_inclui_aviso_consultivo_dentro_de_main_com_fechamento_multilinha(
    tmp_path: Path, report: FindingsReport
) -> None:
    folder = tmp_path / report.run_id
    folder.mkdir()
    (folder / "verification.json").write_text('{"secret": "senha-privada"', encoding="utf-8")
    HtmlReportSink(tmp_path, _builder(tmp_path)).write(report.run_id, report)
    html = (folder / "report.html").read_text(encoding="utf-8")
    parser = _SectionParser()
    parser.feed(html)
    assert parser.section_in_main
    assert "</main>\n</body>\n</html>" in html
    assert "Verificação inválida" in html
    assert "senha-privada" not in html
    assert "Reproduzido" not in html


def test_nuclei_finding_is_presented_with_its_reproduction_and_never_as_independent(
    tmp_path: Path, report: FindingsReport
) -> None:
    from tests.fakes.nuclei import nuclei_finding, nuclei_result

    finding = nuclei_finding(severity="high")
    stored = nuclei_result(findings=(finding,), run_id=report.run_id, product=report.product)
    with_nuclei = report.model_copy(update={"nuclei": stored})
    _write(
        tmp_path,
        report,
        "verification.json",
        {
            "schema_version": 1,
            "product": report.product,
            "run_id": report.run_id,
            "entries": [
                {
                    "fingerprint": finding.fingerprint,
                    "level": "reproduced",
                    "reason": "Reprodução: o mesmo modelo voltou a casar.",
                    "recipe": "nuclei_template",
                }
            ],
        },
    )

    view = _builder(tmp_path).build(with_nuclei)

    (row,) = [item for item in view.findings if item.origin == "nuclei"]
    assert row.finding_id == finding.finding_id
    assert row.title == finding.record.template_id
    assert row.verification.level == "reproduced"
    assert row.verification.recipe == "nuclei_template"
    assert row.confirmations == ()
