"""QA independente (V1.5c): nome hostil em `negative.json` e `error-signals.json` no relatório."""

from html.parser import HTMLParser

import pytest

from harness_dast.application.report import ReportRequest
from harness_dast.domain.negative_result import NegativeNotTested
from harness_dast.domain.report.html import render_html
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.signal_result import ProxySignals, SignalFinding, SignalWindow
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_rig import ScanRig
from tests.unit.domain.negative_samples import accepted, negative_result

HOSTILE = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "</code><iframe src=//evil></iframe>",
    "javascript:alert(1)",
    "<a href=//evil>x</a>",
    "&lt;b&gt; &amp; ‮\u0000\x07",
    "`code`](http://evil) <svg onload=1>",
    "| a | b |\n# titulo\n- item",
    "x" * 5000,
]
FORBIDDEN_TAGS = {"script", "img", "iframe", "svg", "object", "embed", "link", "a", "form", "style"}


def scanned() -> ScanRig:
    rig = ScanRig(flows=agenda_flows())
    rig.run_probe()
    rig.run_scan()
    return rig


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(name for name, _ in attrs)


def _hostile_negative(rig: ScanRig, text: str) -> None:
    run_id = rig.probe_result.run_id
    base = negative_result(product="agenda", run_id=run_id)
    finding = accepted(field=text[:64], title=text[:200]).model_copy(
        update={"operation_id": text, "account": text, "declared": text}
    )
    rig.artifacts.negative[run_id] = base.model_copy(
        update={
            "findings": (finding,),
            "stop_message": text,
            "accounts": (text,),
            "not_tested": (
                NegativeNotTested(
                    operation_id=text,
                    method=text[:10],
                    path=text,
                    reason=text,
                    message=text,
                    field=text,
                ),
            ),
        }
    )


@pytest.mark.parametrize("text", HOSTILE)
def test_a_hostile_text_in_negative_json_never_becomes_markup_in_the_html(text: str) -> None:
    rig = scanned()
    _hostile_negative(rig, text)
    outcome = rig.report().execute(ReportRequest(product="agenda", run_id=rig.probe_result.run_id))

    page = render_html(outcome.report)

    parsed = Collector()
    parsed.feed(page)
    baseline = Collector()
    baseline.feed(render_html(_without_negative(outcome.report)))
    assert FORBIDDEN_TAGS & set(parsed.tags) == FORBIDDEN_TAGS & set(baseline.tags)
    assert not [name for name in parsed.attrs if name.startswith("on")]
    assert "<script" not in page.lower()


def _without_negative(report: FindingsReport) -> FindingsReport:
    return report.model_copy(update={"negative": None})


@pytest.mark.parametrize("text", HOSTILE)
def test_a_hostile_text_in_error_signals_never_becomes_markup_in_the_html(text: str) -> None:
    rig = scanned()
    outcome = rig.report().execute(ReportRequest(product="agenda", run_id=rig.probe_result.run_id))
    finding = SignalFinding(
        finding_id="S-0a1b2c3d",
        fingerprint="0a1b2c3d" + "0" * 56,
        category="sql_error",
        title=text[:200],
        proposed_severity="medium",
        proposed_confidence="medium",
        cwe=209,
        method=text[:10],
        path_template=text,
        occurrences=1,
        statuses=(500,),
        query_params=(text,),
        operation_id=text,
    )
    signals = ProxySignals(
        enabled=True,
        window=SignalWindow(start=text, end=text),
        responses_examined=1,
        responses_skipped={text: 3},
        counts={"sql_error": 1, text: 2},
        findings=(finding,),
        message=text,
    )
    report = outcome.report.model_copy(update={"proxy_signals": signals})

    page = render_html(report)

    parsed = Collector()
    parsed.feed(page)
    baseline = Collector()
    baseline.feed(render_html(outcome.report))
    assert FORBIDDEN_TAGS & set(parsed.tags) == FORBIDDEN_TAGS & set(baseline.tags)
    assert not [name for name in parsed.attrs if name.startswith("on")]
    assert "<script" not in page.lower()


MARKDOWN_HOSTILE = [
    "](http://evil.example/x) [clique](http://evil.example)",
    "\n# Titulo falso\n- item falso",
    "![img](http://evil.example/p.png)",
    "<script>alert(1)</script>",
    "x\r\n\r\n## Resultado: tudo seguro",
]


@pytest.mark.parametrize("text", MARKDOWN_HOSTILE)
def test_a_hostile_text_in_negative_json_never_becomes_a_live_link_or_heading_in_markdown(
    text: str,
) -> None:
    from harness_dast.domain.report.markdown import render_markdown

    rig = scanned()
    _hostile_negative(rig, text)
    outcome = rig.report().execute(ReportRequest(product="agenda", run_id=rig.probe_result.run_id))

    page = render_markdown(outcome.report)
    clean = render_markdown(_without_negative(outcome.report))

    import re

    lines = [line.strip() for line in page.splitlines()]
    assert not [
        line for line in lines if line.startswith(("# Titulo", "- item falso", "## Resultado"))
    ]
    assert len(page.splitlines()) - len(clean.splitlines()) < 400
    live = re.sub(r"`[^`\n]*`", "", page)  # o que está em código não é interpretado
    assert not re.search(r"(?<!\\)!\[", live)
    assert not re.search(r"(?<!\\)\]\(http", live)
    assert not re.search(r"(?<!\\)<script", live)
