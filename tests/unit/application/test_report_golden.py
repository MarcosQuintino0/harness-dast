"""Arquivos de referência de `findings.json` e `report.md` a partir de alertas no formato do spike.

Os alertas em `tests/fixtures/zap_alerts/` são RECONSTRUÍDOS do spike do M0, não capturados (veja
o README de lá). Mudança no relatório aparece no diff dos arquivos `*.golden.*`. Para regravá-los
depois de uma mudança intencional: `HDAST_UPDATE_GOLDEN=1 uv run pytest -k golden`.
"""

import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.sinks import (
    HtmlReportSink,
    JsonFindingsSink,
    MarkdownReportSink,
)
from harness_dast.application.report import Report, ReportRequest
from tests.fakes.clock import FixedClock, utc
from tests.fakes.profile_data import valid_profile
from tests.fakes.profile_repository import InMemoryProfileRepository

FIXTURES = Path(__file__).parents[2] / "fixtures" / "zap_alerts"
RUN_ID = "2026-11-13T05-15-32Z-vampi-ab12"
INPUTS = ("probe.json", "scan.json", "alerts.raw.json", "evidence.json")
GOLDEN = {
    "findings.json": "findings.golden.json",
    "report.md": "report.golden.md",
    "report.html": "report.golden.html",
}


def generate(tmp_path: Path) -> Path:
    directory = tmp_path / RUN_ID
    directory.mkdir()
    for name in INPUTS:
        shutil.copy(FIXTURES / name, directory / name)
    profiles = InMemoryProfileRepository()
    profiles.add(valid_profile("vampi"))
    Report(
        profiles=profiles,
        artifacts=FileRunArtifacts(tmp_path),
        sinks=[
            JsonFindingsSink(tmp_path),
            MarkdownReportSink(tmp_path),
            HtmlReportSink(tmp_path),
        ],
        clock=FixedClock(utc(2026, 11, 13, 6, 0)),
        harness_version="0.0-golden",
    ).execute(ReportRequest(product="vampi", run_id=RUN_ID))
    return directory


def test_findings_json_and_report_md_match_the_golden_files(tmp_path: Path) -> None:
    directory = generate(tmp_path)

    for produced, golden in GOLDEN.items():
        actual = (directory / produced).read_bytes()
        target = FIXTURES / golden
        if os.environ.get("HDAST_UPDATE_GOLDEN") == "1":
            target.write_bytes(actual)
        assert actual == target.read_bytes(), f"{produced} difere de {golden}"


def outside_code_blocks(text: str) -> str:
    kept: list[str] = []
    fence = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not fence and stripped.startswith("```"):
            fence = stripped.rstrip("abcdefghijklmnopqrstuvwxyz")
        elif fence and stripped == fence:
            fence = ""
        elif not fence:
            kept.append(line)
    return "\n".join(kept)


def test_golden_report_shows_the_honest_framing_and_escapes_hostile_content(tmp_path: Path) -> None:
    text = (generate(tmp_path) / "report.md").read_text(encoding="utf-8")
    prose = re.sub(r"(`+)[^`]*\1", "", outside_code_blocks(text))

    assert text.index("## O que este relatório não testou") < text.index("## Achados")
    assert "Varreduras truncadas ou paradas" in text
    assert "Operações sem varredura" in text
    assert "<script>" not in prose
    assert "<img" not in prose
    assert "](http://evil.example)" not in prose


@pytest.mark.parametrize("name", ["README.md", *INPUTS, *GOLDEN.values()])
def test_every_fixture_file_exists(name: str) -> None:
    assert (FIXTURES / name).is_file()


def test_golden_html_is_one_page_with_groups_and_no_script_or_external_reference(
    tmp_path: Path,
) -> None:
    page = (generate(tmp_path) / "report.html").read_text(encoding="utf-8")

    assert "<script" not in page
    found: list[str] = []

    class Collect(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            found.extend([tag, *(name for name, _ in attrs)])

    Collect().feed(page)
    assert not {"script", "img", "link", "iframe", "src", "href"} & set(found)
    assert not [name for name in found if name.startswith("on")]
    assert "Cookie No HttpOnly Flag" in page
    assert "4 achado(s)" in page
    assert "duplo envio" in page
