"""Seção "Valores que o esquema proíbe" no relatório (ADR 0051): JSON, Markdown e HTML."""

import json
import re

from harness_dast.application.report import exceeds
from harness_dast.domain.negative_result import NegativeNotTested, NegativeResult
from harness_dast.domain.report.actions import next_steps
from harness_dast.domain.report.build import assemble_report
from harness_dast.domain.report.html import render_html
from harness_dast.domain.report.markdown import render_markdown
from harness_dast.domain.report.model import (
    NOT_TESTED_NEGATIVE,
    NOT_TESTED_STATEMENTS,
    NOT_TESTED_WITH_AUTHZ,
    FindingsReport,
    build_digest,
)
from tests.fakes.zap_alerts import zap_alert
from tests.unit.application.test_report_authz import authz_result
from tests.unit.domain.negative_samples import accepted, negative_result, server_error
from tests.unit.domain.report.helpers import entry, operation, probe_result, scan_result
from tests.unit.domain.report.test_html import XSS, parse

TITLE = "Valores que o esquema proíbe (técnica própria, determinística)"


def build(
    negative: NegativeResult | None,
    *,
    alerts: list[dict[str, str]] | None = None,
    authz: bool = False,
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
        authz=authz_result(product="vampi") if authz else None,
        negative=negative,
    )


def test_the_report_carries_the_negative_section_apart_from_the_zap_findings() -> None:
    report = build(negative_result())

    assert report.negative is not None
    assert {item.technique for item in report.negative.findings} == {
        "input_accepted",
        "input_server_error",
    }
    assert all(item.origin == "negative" for item in report.negative.findings)
    assert {item.technique for item in report.findings} == {"zap_active_scan"}
    assert report.summary.total == len(report.findings)


def test_the_summary_counts_negative_findings_by_severity_without_touching_the_zap_totals() -> None:
    report = build(negative_result(findings=(accepted(severity="medium"), server_error())))

    assert report.summary.negative_by_severity == {
        "high": 0,
        "medium": 1,
        "low": 1,
        "informational": 0,
        "unknown": 0,
    }
    assert report.summary.by_severity["medium"] == 0


def test_without_the_stage_the_report_has_no_negative_field_content() -> None:
    report = build(None)

    assert report.negative is None
    assert report.summary.negative_by_severity == {}
    assert report.not_tested_statements == NOT_TESTED_STATEMENTS


def test_with_the_stage_the_statements_gain_where_it_touched_and_where_it_did_not() -> None:
    report = build(negative_result(findings=()))

    assert report.not_tested_statements == (*NOT_TESTED_STATEMENTS, NOT_TESTED_NEGATIVE)
    assert "formulário" in NOT_TESTED_NEGATIVE
    assert "NÃO é evidência" in report.not_tested_statements[-2]


def test_with_authz_and_the_stage_both_statements_are_kept_in_order() -> None:
    report = build(negative_result(findings=()), authz=True)

    assert report.not_tested_statements == (*NOT_TESTED_WITH_AUTHZ, NOT_TESTED_NEGATIVE)


def test_a_report_from_before_the_stage_still_parses() -> None:
    data = json.loads(build(negative_result()).model_dump_json())
    del data["negative"]
    del data["summary"]["negative_by_severity"]

    old = FindingsReport.model_validate(data)

    assert old.negative is None
    assert old.summary.negative_by_severity == {}


def test_the_gate_counts_negative_findings_even_when_the_zap_found_nothing() -> None:
    quiet = build(negative_result(findings=()), alerts=[])
    loud = build(negative_result(findings=(accepted(severity="medium"),)), alerts=[])

    assert exceeds(quiet, "low") is False
    assert exceeds(loud, "medium") is True
    assert exceeds(loud, "high") is False
    assert exceeds(loud, "none") is False


def test_the_digest_exposes_the_negative_result() -> None:
    digest = build_digest(build(negative_result()), ("findings.json",), "none", exceeds=False)

    assert digest.negative is not None
    assert len(digest.negative.findings) == 2


def test_the_markdown_names_the_technique_the_field_and_never_the_sent_value() -> None:
    text = render_markdown(build(negative_result()))

    assert f"## {TITLE}" in text
    assert "input_accepted" in text
    assert "input_server_error" in text
    assert "`limite`" in text
    assert "maximum 100" in text
    assert "o valor enviado não foi gravado" in text
    assert "Limites desta técnica" in text
    assert "writes_not_authorized" in text
    assert "| Classe do valor | Enviados | Rejeitados | Aceitos | 5xx | Sem conclusão |" in text
    assert "| `GET /api/produtos` | 2 | 1 | 1 | 0 | 0 |" in text
    assert "Valores que o esquema proíbe (técnica própria, não é do ZAP):" in text


def test_the_markdown_without_the_stage_has_no_negative_section() -> None:
    text = render_markdown(build(None))

    assert TITLE not in text
    assert "Valores que o esquema proíbe" not in text


def test_the_markdown_with_no_finding_says_to_read_what_was_not_tested() -> None:
    text = render_markdown(build(negative_result(findings=()), alerts=[]))

    assert "Nenhum achado de valor proibido" in text
    assert "Nenhum achado do ZAP" in text


def test_the_markdown_warns_about_resources_a_post_may_have_left() -> None:
    text = render_markdown(build(negative_result(created=2)))

    assert "pode ter criado 2 recurso(s)" in text
    assert "hdast cleanup" in text


def test_the_markdown_says_when_a_put_was_not_restored() -> None:
    finding = accepted(method="PUT", restored=False, created=False, severity="medium")

    text = render_markdown(build(negative_result(findings=(finding,))))

    assert "NÃO confirmada" in text


def test_a_stopped_stage_shows_its_state_and_stop_message() -> None:
    text = render_markdown(build(negative_result(status="stopped_deadline")))

    assert "Estado: stopped\\_deadline." in text
    assert "Parada: parou" in text


def test_the_html_has_the_section_cards_and_the_summary_bullet() -> None:
    page = render_html(build(negative_result()))

    assert f"<h2>{TITLE}</h2>" in page
    assert "Valores que o esquema proíbe (técnica própria, não é do ZAP):" in page
    assert "Varredura ativa do ZAP:" in page
    assert "Valores que o esquema proíbe: estado completed, 2 achado(s), 1 item(ns)" in page
    assert "<code>input_accepted</code>" in page
    assert "<code>input_server_error</code>" in page
    assert "não é achado do ZAP" in page


def test_the_html_without_the_stage_says_it_did_not_run() -> None:
    page = render_html(build(None))

    assert "Valores que o esquema proíbe: não rodou" in page
    assert f"<h2>{TITLE}</h2>" not in page


def test_the_html_stays_self_contained_with_the_section() -> None:
    page = render_html(build(negative_result()))

    parsed = parse(page)
    assert "script" not in parsed.tags
    assert "default-src 'none'" in page


def test_hostile_text_in_a_negative_finding_is_escaped_in_both_formats() -> None:
    hostile = accepted(field=XSS, title=XSS)
    notes = (NegativeNotTested(reason="budget", message=XSS, field=XSS),)
    report = build(negative_result(findings=(hostile,), not_tested=notes))

    page = render_html(report)
    text = render_markdown(report)

    assert "<script>" not in page
    assert "<img" not in page
    prose = re.sub(r"(`+)[^`]*\1", "", text)
    assert not re.search(r"(?<!\\)<(script|img)", prose)


def test_the_next_steps_ask_for_triage_and_cleanup_without_widening_anything() -> None:
    steps = next_steps(build(negative_result(created=1)))
    joined = " ".join(steps)

    assert "valores que o esquema proíbe" in joined
    assert "hdast cleanup" in joined
    assert "não pôde testar" in joined
    assert "coerção" in joined
    assert "sem ampliar escopo, limites nem janela sem nova autorização" in joined.lower()


def test_a_report_with_only_negative_findings_does_not_claim_there_are_none() -> None:
    steps = next_steps(build(negative_result(), alerts=[]))

    assert not any(step.startswith("Nenhum achado não é prova") for step in steps)


def test_a_stopped_stage_is_flagged_in_the_next_steps() -> None:
    steps = next_steps(build(negative_result(status="stopped_window")))

    assert any("parou antes do fim" in step and "validado" in step for step in steps)
