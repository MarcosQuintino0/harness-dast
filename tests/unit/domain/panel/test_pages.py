"""Registro de páginas: todas as abas existem, os links não quebram, texto hostil não vira HTML."""

import html
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from harness_dast.domain.panel.build import build_panel_view
from harness_dast.domain.panel.model import PanelCommand, PanelExplanation, PanelView
from harness_dast.domain.panel.pages import PAGES, PanelPage, render_panel
from harness_dast.domain.panel.sources import PanelSources
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.scan_result import ScanResult
from tests.unit.domain.panel.helpers import (
    BIDI,
    XSS,
    bare,
    findings_report,
    run_summary,
    sources,
    spec_operations,
)
from tests.unit.domain.report_helpers import entry, scan_result

EXPECTED_FILES = (
    "summary.html",
    "stages.html",
    "findings.html",
    "coverage.html",
    "authorization.html",
    "terminal.html",
    "time-and-tokens.html",
)
INDEX_LINKS = {"../../index.html", "../../history-vampi.html"}
"""Destinos fora de `panel/`: os índices, que `hdast panel` regrava junto com as páginas."""
SAFE_ATTRIBUTES = {
    "class", "href", "style", "lang", "charset", "name", "content", "http-equiv", "role",
    "aria-label", "aria-current", "id", "open",
}  # fmt: skip
FORBIDDEN_TAGS = {"script", "link", "img", "iframe", "object", "embed", "form", "svg", "base"}


class Markup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str | None]] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes += attrs
        self.links += [value or "" for name, value in attrs if name == "href"]


def markup(page: str) -> Markup:
    parser = Markup()
    parser.feed(page)
    return parser


def hostile_sources() -> PanelSources:
    base = sources()
    finding = base.findings.findings[0]  # type: ignore[union-attr]
    proof = finding.evidence.model_copy(
        update={"available": True, "zap_evidence": XSS, "attack": XSS, "response_body": XSS}
    )
    changed = finding.model_copy(
        update={
            "finding_id": 'F-"><script>x</script>',
            "title": f"{XSS}{BIDI}",
            "parameter": XSS,
            "path_template": f"/x/{XSS}",
            "description": XSS,
            "evidence": proof,
        }
    )
    report = base.findings.model_copy(update={"findings": (changed,)})  # type: ignore[union-attr]
    operations = spec_operations(summary=f"{XSS}{BIDI}", tag=XSS)
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="failed", message=f"{XSS}{BIDI}\x1b[31m"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="done" if False else "ok"),
        ),
    )
    return PanelSources(
        product="vampi",
        run_id=base.run_id,
        timezone=base.timezone,
        summary=summary,
        probe=base.probe,
        scan=base.scan,
        findings=report,
        operations=operations,
        commands=(PanelCommand(command=XSS, translation=XSS, output=XSS),),
        explanations={
            'F-"><script>x</script>': PanelExplanation(
                title=XSS, technical_name=XSS, what_happened=XSS, what_to_do=XSS, who=XSS
            )
        },
    )


def scenarios() -> dict[str, PanelSources]:
    stopped = scan_result(
        [entry("obter", "GET", "/users/v1/{username}", 4, outcome="truncated")],
        status="stopped_deadline",
    ).model_copy(update={"stop_message": f"{XSS}{BIDI}"})
    failed = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="failed", message=XSS),
            StageRecord(name="probe", status="not_run"),
            StageRecord(name="scan", status="not_run"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )
    clean = findings_report(alerts=[])
    return {
        "happy": sources(),
        "hostile": hostile_sources(),
        "partial-file-only": sources(summary=None, scan=stopped),
        "error": sources(summary=failed, probe=None, scan=None, findings=None),
        "no-severe": sources(findings=clean),
        "bare": bare(),
    }


@pytest.fixture(params=sorted(scenarios()))
def pages(request: pytest.FixtureRequest) -> dict[str, str]:
    return dict(render_panel(build_panel_view(scenarios()[request.param])))


def test_the_registry_has_the_six_design_pages_in_the_menu_order() -> None:
    assert tuple(page.file for page in PAGES) == EXPECTED_FILES
    assert [page.label for page in PAGES] == [
        "Resumo", "Etapas", "Falhas", "Cobertura", "Autorização", "Terminal", "Tempo e tokens",
    ]  # fmt: skip
    assert all(isinstance(page, PanelPage) for page in PAGES)


def test_every_scenario_renders_every_page(pages: dict[str, str]) -> None:
    assert tuple(pages) == EXPECTED_FILES
    assert all(text.startswith("<!doctype html>") for text in pages.values())


def test_every_page_has_the_shell_and_exactly_one_current_tab(pages: dict[str, str]) -> None:
    for name, text in pages.items():
        parsed = markup(text)
        current = [value for key, value in parsed.attributes if key == "aria-current"]
        assert current == ["page"], name
        assert 'lang="pt-BR"' in text
        assert "default-src 'none'" in text


def test_menu_links_never_break_every_link_points_to_a_generated_page(
    pages: dict[str, str],
) -> None:
    for name, text in pages.items():
        parsed = markup(text)
        for link in parsed.links:
            if link == "../report.html" or link in INDEX_LINKS:  # fora de `panel/`
                continue
            target, _, anchor = link.partition("#")
            assert (target or name) in pages, (name, link)
            if anchor:  # a âncora existe na página de destino
                assert f'id="{html.escape(anchor)}"' in pages[target or name], (name, link)


def test_summary_and_coverage_link_the_severe_finding_to_its_anchor_in_the_findings_page() -> None:
    rendered = render_panel(build_panel_view(sources()))
    finding_id = build_panel_view(sources()).severe[0].finding_id

    for name in ("summary.html", "coverage.html"):
        assert f"findings.html#{finding_id}" in markup(rendered[name]).links, name
    assert f'id="{finding_id}"' in rendered["findings.html"]


def test_no_page_has_script_external_resource_or_event_handler(pages: dict[str, str]) -> None:
    for name, text in pages.items():
        parsed = markup(text)
        assert "<script" not in text.lower(), name
        assert not FORBIDDEN_TAGS & set(parsed.tags), name
        assert not re.search(r"https?://", text), name
        assert "onclick" not in text.lower(), name
        assert {key for key, _ in parsed.attributes} <= SAFE_ATTRIBUTES, name


def test_no_page_says_safe_or_approved(pages: dict[str, str]) -> None:
    for name, text in pages.items():
        visible = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
        assert not re.search(r"\b(seguro|segura|aprovad[oa])\b", visible, flags=re.I), name


def test_hostile_text_is_escaped_in_every_page() -> None:
    rendered = render_panel(build_panel_view(hostile_sources()))

    for name, text in rendered.items():
        assert "<script" not in text, name
        assert "<img" not in text, name
        assert "‮" not in text, name
        assert "\x1b" not in text, name
        assert not any(key.startswith("on") for key, _ in markup(text).attributes), name
    assert "&lt;script&gt;" in rendered["summary.html"]


def test_hostile_finding_id_cannot_break_out_of_the_link_attribute() -> None:
    summary = render_panel(build_panel_view(hostile_sources()))["summary.html"]

    assert "findings.html#F-&quot;&gt;&lt;script&gt;" in summary
    assert '"><script' not in summary


def test_the_findings_tab_counter_is_the_number_of_severe_findings() -> None:
    summary = render_panel(build_panel_view(sources()))["summary.html"]
    nothing = render_panel(build_panel_view(sources(findings=findings_report(alerts=[]))))

    assert re.search(r'Falhas<span class="cnt">1</span>', summary)
    assert re.search(r'Falhas<span class="cnt"[^>]*>0</span>', nothing["summary.html"])


def test_a_scan_result_type_is_what_the_partial_scenario_uses() -> None:
    assert isinstance(scenarios()["partial-file-only"].scan, ScanResult)


def test_view_type_is_the_single_input_of_every_renderer() -> None:
    view = build_panel_view(sources())

    assert isinstance(view, PanelView)
    assert all(isinstance(page.render(view), str) for page in PAGES)


def test_rendering_is_deterministic() -> None:
    view = build_panel_view(sources())

    assert render_panel(view) == render_panel(view)


def test_design_files_exist_for_every_registered_page() -> None:
    folder = Path(__file__).parents[4] / "docs" / "design" / "execution-panel" / "screens"

    assert all((folder / name).is_file() for name in EXPECTED_FILES)
