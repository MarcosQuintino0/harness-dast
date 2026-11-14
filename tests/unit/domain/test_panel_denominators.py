"""Os números de função têm um nome só em todas as telas: sistema, tentadas, responderam, atacadas.

Antes, o Ao vivo dizia "de 28", o Resumo "9 de 30" e as Etapas "29 de 30" para coisas diferentes.
"""

import re

from harness_dast.domain.panel_build import build_panel_view
from harness_dast.domain.panel_model import PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.scan_result import PlannedScan
from tests.unit.domain.panel_helpers import run_summary, sources

PLANNED = 28


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def planned_view(*, partial: bool = False) -> PanelView:
    base = sources()
    assert base.scan is not None
    planned = tuple(
        PlannedScan(operation_id=f"op{n}", method="GET", path=f"/p/{n}") for n in range(PLANNED)
    )
    changes: dict[str, object] = {"scan": base.scan.model_copy(update={"planned": planned})}
    if partial:
        changes["summary"] = run_summary(
            status="failed",
            stages=(
                StageRecord(name="preflight", status="ok"),
                StageRecord(name="probe", status="ok"),
                StageRecord(name="scan", status="failed", message="acabou o tempo"),
                StageRecord(name="authz", status="not_run"),
                StageRecord(name="report", status="not_run"),
            ),
        )
    return build_panel_view(sources(**changes))


def test_the_verdict_counts_the_functions_the_scan_planned_to_attack() -> None:
    assert planned_view().verdict.functions_planned == PLANNED


def test_the_summary_counts_attacked_functions_against_the_planned_ones() -> None:
    text = main_text(render_panel(planned_view())["summary.html"])

    assert f"1 de {PLANNED} funções atacadas" in text
    assert "das planejadas pela varredura" in text


def test_the_partial_summary_uses_the_same_planned_number() -> None:
    text = main_text(render_panel(planned_view(partial=True))["summary.html"])

    assert f"com 1 de {PLANNED} funções atacadas" in text


def test_the_stages_use_the_same_names_for_each_number() -> None:
    text = main_text(render_panel(planned_view())["stages.html"])

    assert f"1 de {PLANNED} funções planejadas atacadas" in text
    assert re.search(r"Tentou \d+ funções? \(de \d+ no sistema\); \d+ de \d+ responderam", text)


def test_the_coverage_names_the_swagger_number_as_the_system_functions() -> None:
    text = main_text(render_panel(planned_view())["coverage.html"])

    assert "funções do sistema (no Swagger)" in text


def test_the_history_counts_the_attacked_functions_against_the_planned_ones() -> None:
    from harness_dast.domain.panel_index_build import row_from_view

    row = row_from_view(planned_view(), incomplete=False, panel_link=None)

    assert row.functions_basis == PLANNED
