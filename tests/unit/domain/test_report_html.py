"""`report.html`: página autocontida, em português, sem script e com escape rigoroso."""

import re
from html.parser import HTMLParser

import pytest

from harness_dast.domain.finding import Finding, TriageNote
from harness_dast.domain.html_safe import block, ident, plain, text
from harness_dast.domain.report_actions import next_steps
from harness_dast.domain.report_build import assemble_report
from harness_dast.domain.report_html import render_html
from harness_dast.domain.report_model import FindingsReport
from harness_dast.domain.traffic import TrafficSummary
from tests.fakes.zap_alerts import zap_alert
from tests.unit.domain.report_helpers import entry, operation, probe_result, scan_result

XSS = "<script>alert(1)</script><img src=x onerror=alert(1)>\"'&"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlMTIzNDU2"


def report(alerts: list[dict[str, str]], **changes: object) -> FindingsReport:
    ops = [operation("obter", "GET", "/users/v1/{username}")]
    built = assemble_report(
        probe=probe_result(ops),
        scan=scan_result([entry("obter", "GET", "/users/v1/{username}", 4, alert_ids=("9",))]),
        raw_alerts=alerts,
        evidence={},
        triage=None,
        baseline=None,
        generated_at="2026-11-13T06:00:00+00:00",
        harness_version="0.0-test",
        auth_header=("Authorization", "Bearer $TOKEN"),
        csrf_header=None,
    )
    return built.model_copy(update=changes)


def hostile(base: FindingsReport) -> FindingsReport:
    item = base.findings[0]
    proof = item.evidence.model_copy(
        update={
            "available": True,
            "attack": XSS,
            "zap_evidence": XSS,
            "request_header": f"POST /x HTTP/1.1\nAuthorization: Bearer {JWT}",
            "response_header": f"HTTP/1.1 500 {XSS}",
            "response_body": f"{XSS}\n</pre><script>alert(2)</script> token={JWT}",
        }
    )
    changed = item.model_copy(
        update={
            "title": XSS,
            "parameter": XSS,
            "description": XSS,
            "solution": XSS,
            "path_template": f"/x/{XSS}",
            "evidence": proof,
            "reproduce_curl": f"curl '{XSS}' -H 'Authorization: Bearer {JWT}'",
            "triage": TriageNote(note=XSS, reason=XSS, suspected_false_positive=True),
        }
    )
    from harness_dast.domain.finding_group import group_findings

    return base.model_copy(update={"findings": (changed,), "groups": group_findings((changed,))})


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs += attrs


def parse(page: str) -> Tags:
    parser = Tags()
    parser.feed(page)
    return parser


def test_page_is_self_contained_with_no_script_and_no_external_resource() -> None:
    page = render_html(report([zap_alert("9")]))

    parsed = parse(page)
    assert page.startswith("<!doctype html>")
    assert "script" not in parsed.tags
    assert not {"link", "iframe", "object", "embed", "form", "img"} & set(parsed.tags)
    assert not re.search(r"(?i)\b(?:src|href|action)\s*=", page)
    assert "http://" not in page.replace("http://evil", "")
    assert "default-src 'none'" in page
    assert "prefers-color-scheme: dark" in page
    assert 'name="viewport"' in page
    assert 'lang="pt-BR"' in page


def test_page_has_the_requested_sections_in_portuguese() -> None:
    page = render_html(report([zap_alert("9")]))

    for heading in (
        "Resumo",
        "O que fazer agora",
        "Achados por gravidade",
        "O que a varredura NÃO cobriu",
        "Tráfego recusado pela cerca de escopo",
    ):
        assert f"<h2>{heading}</h2>" in page
    assert "força" in page
    assert "req/s" in page


def test_hostile_target_text_cannot_become_markup() -> None:
    page = render_html(hostile(report([zap_alert("9")])))

    parsed = parse(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert not any(name.startswith("on") for name, _ in parsed.attrs)
    assert "<script" not in page
    assert "Como reproduzir" in page
    assert "&lt;script&gt;" in page
    assert "&lt;/pre&gt;" in page
    assert "</pre><script" not in page


def test_secrets_never_reach_the_page() -> None:
    page = render_html(hostile(report([zap_alert("9")])))

    assert JWT not in page
    assert "eyJhbGci" not in page
    assert "***" in page


def test_hostile_text_in_coverage_and_traffic_fields_is_escaped() -> None:
    base = report([zap_alert("9")])
    coverage = base.coverage.model_copy(
        update={
            "scan_stop_message": XSS,
            "partial": True,
            "traffic": TrafficSummary(
                enabled=True, allowed=3, denied=2, denied_by_reason={XSS: 1, "fora_do_escopo": 1}
            ),
        }
    )

    page = render_html(base.model_copy(update={"coverage": coverage}))

    assert "script" not in parse(page).tags
    assert "&lt;script&gt;" in page
    assert "Relatório parcial" in page
    assert "fora_do_escopo" in page


def test_denied_traffic_is_listed_by_reason_for_any_reason_text() -> None:
    base = report([zap_alert("9")])
    traffic = TrafficSummary(
        enabled=True, allowed=10, denied=7, denied_by_reason={"host": 4, "metodo": 2, "novo": 1}
    )
    page = render_html(
        base.model_copy(update={"coverage": base.coverage.model_copy(update={"traffic": traffic})})
    )

    assert "<b>7</b> pedido(s) do varredor foram recusados" in page
    for reason in ("host", "metodo", "novo"):
        assert f"<td>{reason}</td>" in page


def test_traffic_not_measured_and_no_denials_are_stated_plainly() -> None:
    page = render_html(report([]))
    assert "Não medido" in page

    base = report([])
    traffic = TrafficSummary(enabled=True, allowed=5)
    quiet = render_html(
        base.model_copy(update={"coverage": base.coverage.model_copy(update={"traffic": traffic})})
    )
    assert "Nenhum pedido foi recusado" in quiet


def test_no_findings_page_says_that_it_proves_nothing() -> None:
    page = render_html(report([]))

    assert "Nenhum achado" in page
    assert "NÃO prova" in page
    assert "<article" not in page


def test_grouped_findings_show_count_locations_and_the_fixed_note() -> None:
    cookies = [
        zap_alert(
            str(i),
            pluginId="10010",
            alertRef="10010",
            alert="Cookie No HttpOnly Flag",
            cweid="1004",
            risk="Low",
            param="XSRF-TOKEN",
            inputVector="",
            sourceMessageId="4",
            url=f"https://h/p{i}",
        )
        for i in (1, 2)
    ]
    page = render_html(report(cookies))

    assert "Cookie No HttpOnly Flag" in page
    assert "duplo envio" in page
    assert "Onde aparece" in page
    assert page.count("<article") == 1


def test_severity_is_shown_as_proposed_and_never_rewritten() -> None:
    base = report([zap_alert("9")])
    page = render_html(base)

    assert base.findings[0].proposed_severity == "high"
    assert "Gravidade alta" in page
    assert "PROPOSTAS pelo ZAP" in page


def test_unknown_origin_findings_and_missing_evidence_do_not_break_the_page() -> None:
    base = report([zap_alert("9")])
    bare = base.findings[0].model_copy(
        update={
            "evidence": base.findings[0].evidence.model_copy(update={"available": False}),
            "reproduce_curl": None,
            "operation_id": None,
            "plugin_id": "hdast-authz",
            "alert_ref": "hdast-authz-1",
        }
    )
    from harness_dast.domain.finding_group import group_findings

    page = render_html(
        base.model_copy(update={"findings": (bare,), "groups": group_findings((bare,))})
    )

    assert "não foram guardadas" in page
    assert "Como reproduzir" not in page
    assert "hdast-authz-1" in page


def test_next_steps_follow_the_report_and_never_widen_scope() -> None:
    base = report([zap_alert("9")])
    partial = base.coverage.model_copy(update={"partial": True, "reachability_all": 0.4})

    steps = next_steps(base.model_copy(update={"coverage": partial}))
    joined = " ".join(steps)

    assert "parou antes do fim" in steps[0]
    assert "ALTA" in joined
    assert "40%" in joined
    assert "sem ampliar escopo" in joined
    assert steps[-1].startswith("Registre a triagem")


@pytest.mark.parametrize("value", ["a\x1b[31mb", "a‮b", "x\ny", "a\x00b"])
def test_text_helpers_strip_control_and_bidi(value: str) -> None:
    for fn in (text, block, ident):
        out = fn(value)
        assert "\x1b" not in out
        assert "‮" not in out
        assert "\x00" not in out
    assert "\n" not in text(value)


def test_text_helpers_escape_the_five_html_characters_and_cut() -> None:
    assert text("<&>\"'") == "&lt;&amp;&gt;&quot;&#x27;"
    assert plain("<b>") == "&lt;b&gt;"
    assert ident("a" * 500, 10) == "a" * 9 + "…"
    assert block("linha1\nlinha2") == "linha1\nlinha2"


def test_text_redacts_known_secret_shapes_before_cutting() -> None:
    assert JWT not in text(f"x {JWT}", 15)
    assert "Bearer ***" in text("Authorization: Bearer abcdefgh12345678")


def test_run_ids_and_long_operation_ids_are_not_masked() -> None:
    run_id = "2026-11-13T05-15-32Z-vampi-ab12"
    assert ident(run_id) == run_id
    assert render_html(report([])).count(run_id) >= 1


def test_finding_fixture_type_is_a_finding() -> None:
    assert isinstance(report([zap_alert("9")]).findings[0], Finding)
