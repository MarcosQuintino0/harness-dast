"""Seção "Nuclei" no relatório (ADR 0122): JSON, Markdown e HTML, sem conteúdo do alvo."""

import re

import pytest

from harness_dast.application.report import exceeds
from harness_dast.domain.nuclei_findings import (
    NucleiFinding,
    TechnologyDetected,
    classify,
    parse_nuclei_jsonl,
)
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.report.actions import next_steps
from harness_dast.domain.report.build import assemble_report
from harness_dast.domain.report.html import render_html
from harness_dast.domain.report.markdown import render_markdown
from harness_dast.domain.report.model import (
    NOT_TESTED_NUCLEI,
    NOT_TESTED_STATEMENTS,
    FindingsReport,
    build_digest,
)
from tests.fakes.nuclei import nuclei_finding, nuclei_result, result_line
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report.helpers import entry, operation, probe_result, scan_result
from tests.unit.domain.report.test_html import XSS, parse

TITLE = "Nuclei (segundo motor, modelos conhecidos de exposição)"
SECRET_MARKERS = ("CURL-SEGREDO", "REQ-SEGREDO", "RESP-SEGREDO", "EXTRAIDO-SEGREDO")


def build(
    nuclei: NucleiResult | None, *, alerts: list[dict[str, str]] | None = None
) -> FindingsReport:
    ops = [operation("obter", "GET", "/users/v1/{username}")]
    return assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))]),
        raw_alerts=alerts if alerts is not None else [zap_alert("9", risk="Low")],
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=("Authorization", "Bearer $TOKEN"),
        csrf_header=None,
        nuclei=nuclei,
    )


def technology(template_id: str = "tech-detect", path: str = "/") -> TechnologyDetected:
    line = result_line(template_id, severity="info", path=path, **{"type": "detection"})
    item = classify(parse_nuclei_jsonl(line))
    assert isinstance(item, TechnologyDetected)
    return item


def with_findings(
    *findings: NucleiFinding, technologies: tuple[TechnologyDetected, ...] = ()
) -> NucleiResult:
    return nuclei_result(findings=findings).model_copy(update={"technologies": technologies})


def test_the_report_carries_the_nuclei_section_apart_from_the_zap_findings() -> None:
    nuclei = with_findings(nuclei_finding(severity="high"), nuclei_finding("b", severity="low"))

    report = build(nuclei)

    assert report.nuclei == nuclei
    assert report.summary.nuclei_by_severity["high"] == 1
    assert report.summary.nuclei_by_severity["low"] == 1
    assert report.summary.total == 1
    assert {item.technique for item in report.findings} == {"zap_active_scan"}
    assert NOT_TESTED_NUCLEI in report.not_tested_statements


def test_without_nuclei_the_report_has_no_section_and_the_old_statements() -> None:
    report = build(None)

    assert report.nuclei is None
    assert report.summary.nuclei_by_severity == {}
    assert report.not_tested_statements == NOT_TESTED_STATEMENTS
    assert TITLE not in render_markdown(report)
    assert "Nuclei" not in render_html(report)


def test_markdown_groups_findings_by_severity_with_model_method_path_and_count() -> None:
    nuclei = with_findings(
        nuclei_finding("springboot-env", severity="critical", path="/actuator/env"),
        nuclei_finding("git-config", severity="low", path="/.git/config"),
    )

    text = render_markdown(build(nuclei))

    assert f"## {TITLE}" in text
    assert text.index("### Gravidade alta (1)") < text.index("### Gravidade baixa (1)")
    assert "`springboot-env`" in text
    assert "`GET /actuator/env`" in text
    assert "**Ocorrências:** 1" in text
    assert "reprodução, não confirmação independente" in text
    assert "| Alta | 1 |" in text.split("Nuclei (segundo motor, não é do ZAP):")[1]


def test_the_extracted_value_shows_only_the_count_and_the_bytes() -> None:
    nuclei = with_findings(nuclei_finding(severity="high"))
    report = build(nuclei)

    markdown = render_markdown(report)
    page = render_html(report)

    expected = f"1 valor(es) extraído(s), {len('EXTRAIDO-SEGREDO')} byte(s)"
    assert expected in markdown.replace("\\", "")
    assert expected in page
    for marker in SECRET_MARKERS:
        assert marker not in markdown
        assert marker not in page
        assert marker not in report.model_dump_json()
        assert marker not in build_digest(report, (), "none", exceeds=False).model_dump_json()


def test_technologies_are_listed_apart_and_are_not_findings() -> None:
    nuclei = with_findings(
        technologies=(technology("tech-detect", "/"), technology("nginx-version", "/x"))
    )
    report = build(nuclei)

    markdown = render_markdown(report)
    page = render_html(report)

    assert "### Tecnologias identificadas (não são achados e não entram no gate)" in markdown
    assert "`tech-detect`" in markdown
    assert "Tecnologias identificadas" in page
    assert report.summary.nuclei_by_severity == {
        "high": 0,
        "medium": 0,
        "low": 0,
        "informational": 0,
        "unknown": 0,
    }
    assert exceeds(report.model_copy(update={"findings": ()}), "low") is False
    assert "Nenhum achado do Nuclei" in markdown


def test_html_shows_the_cards_and_the_section() -> None:
    nuclei = with_findings(nuclei_finding(severity="high"), technologies=(technology(),))

    page = render_html(build(nuclei))

    assert f"<h2>{TITLE}</h2>" in page
    assert "Nuclei (segundo motor, não é do ZAP):" in page
    assert "tecnologia(s) identificada(s)" in page
    assert "<code>GET /actuator/env</code>" in page


def test_the_gate_counts_a_high_nuclei_finding_with_the_zap_quiet() -> None:
    quiet = build(with_findings(nuclei_finding(severity="high")), alerts=[])
    mid = build(with_findings(nuclei_finding(severity="medium")), alerts=[])

    assert exceeds(quiet, "high") is True
    assert exceeds(mid, "high") is False
    assert exceeds(mid, "medium") is True
    assert exceeds(quiet, "none") is False


def test_next_steps_mention_the_nuclei_triage_and_the_reproduction() -> None:
    nuclei = with_findings(nuclei_finding(severity="high"), technologies=(technology(),))

    steps = " ".join(next_steps(build(nuclei)))

    assert "achado(s) do Nuclei" in steps
    assert "reprodução, não confirmação independente" in steps
    assert "tecnologia(s)" in steps


def test_a_stopped_stage_is_shown_and_asked_about() -> None:
    nuclei = nuclei_result("stopped_kill", findings=(), message="KILL acionado")

    report = build(nuclei)

    assert "parado pelo KILL" in render_markdown(report)
    assert "O Nuclei parou antes do fim" in " ".join(next_steps(report))


HOSTILE_FIELDS = {
    "matcher-name": "<script>alert(1)</script>](http://evil.example) `x` | a",
    "template-path": "http/<img src=x onerror=alert(1)>.yaml",
}


def hostile_finding() -> NucleiFinding:
    line = result_line("springboot-env", severity="high", **HOSTILE_FIELDS)
    item = classify(parse_nuclei_jsonl(line))
    assert isinstance(item, NucleiFinding)
    return item


def test_html_escapes_every_field_that_comes_from_the_target() -> None:
    page = render_html(build(with_findings(hostile_finding(), technologies=(technology(),))))

    parsed = parse(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert "<script" not in page.lower()
    assert "onerror=alert(1)>" not in page
    assert XSS not in page


@pytest.mark.parametrize("field", ["matcher-name", "template-path"])
def test_markdown_never_turns_target_text_into_a_live_link_or_html(field: str) -> None:
    line = result_line("springboot-env", severity="high", **{field: HOSTILE_FIELDS[field]})
    item = classify(parse_nuclei_jsonl(line))
    assert isinstance(item, NucleiFinding)

    text = render_markdown(build(with_findings(item)))

    live = re.sub(r"(`+).*?\1", "", text)  # o que está em código não é interpretado
    assert not re.search(r"(?<!\\)\]\(http", live)
    assert not re.search(r"(?<!\\)<(script|img)", live)
    assert "\n# " not in text.split(f"## {TITLE}")[1]
