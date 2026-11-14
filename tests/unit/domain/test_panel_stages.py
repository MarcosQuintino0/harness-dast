"""Aba Etapas: fiel a `screens/stages.html` e aos estados de `system/states.html`."""

import re
from pathlib import Path

import pytest

from harness_dast.domain.panel_model import PanelCommand, PanelFunction, PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.panel_stages import render_stages, render_track
from harness_dast.domain.probe_result import ArtifactHashes, RunManifest
from harness_dast.domain.rule_stats import RuleTotal
from harness_dast.domain.run import RunLimits
from harness_dast.domain.run_summary import StageRecord
from tests.unit.domain.panel_helpers import run_summary, sources, view
from tests.unit.domain.test_panel_summary import EXTRA_CLASSES, analyse, main_text

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "screens"


def stages_html(panel_view: PanelView | None = None) -> str:
    return render_panel(panel_view or view())["stages.html"]


def functions(count: int, severe: int = 0) -> tuple[PanelFunction, ...]:
    return tuple(
        PanelFunction(
            operation_id=f"op{n}",
            method="GET",
            path=f"/p/{n}",
            name=f"op{n}",
            area="Outras",
            state="severe" if n < severe else "tested",
        )
        for n in range(count)
    )


def rule(
    plugin_id: int, name: str, alerts: int, *, completed: int = 1, skipped: int = 0
) -> RuleTotal:
    return RuleTotal(
        plugin_id=plugin_id, name=name, time_ms=1000, requests=10, alerts=alerts, operations=1,
        completed=completed, skipped=skipped, interrupted=0, pending=0, unknown=0,
    )  # fmt: skip


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = analyse((DESIGN / "stages.html").read_text(encoding="utf-8"))
    generated = analyse(stages_html())

    assert generated.classes <= design.classes | EXTRA_CLASSES | {"cnt", "k-no"}
    assert {"track", "seg", "stg", "nb", "tm", "grid", "dotk"} <= generated.classes


def test_the_tab_is_called_etapas_and_the_headings_follow_the_design() -> None:
    generated = analyse(stages_html())

    assert generated.tabs[1] == "Etapas"
    assert generated.headings == [
        "As 5 etapas, no tamanho do tempo que levaram",
        "O que aconteceu em cada etapa",
        "Onde o teste travou",
        "Tipos de teste feitos",
    ]


def test_the_five_stages_have_number_title_summary_and_time() -> None:
    page = stages_html()

    assert page.count('<div class="stg"') == 5
    for number in "12345":
        assert re.search(rf'<span class="nb[^"]*">{number}</span>', page)
    for title in (
        "Leu o Swagger e a carta e conferiu o login",
        "Alcance: fez o sistema responder de verdade",
        "Varredura: atacou com o ZAP",
        "Organizou os achados",
    ):
        assert title in page
    assert '<div class="tm"><b>19 min</b>' in page
    assert '<div class="tm"><b>1 min</b>' in page


def test_the_stage_summaries_carry_the_numbers_of_the_run() -> None:
    text = main_text(stages_html())

    assert "Tentou 3 funções (de 5 no sistema); 2 de 3 responderam como esperado." in text
    assert "1 função atacada" in text
    assert "1 achado agrupado por causa (1 causa): 1 graves" in text
    assert "Achou 5 funções." in text
    assert "1 função ficou fora do combinado." in text


def test_the_scan_stage_draws_one_square_per_attacked_function_with_a_label() -> None:
    panel_view = view().model_copy(update={"functions": functions(26, severe=3)})

    page = stages_html(panel_view)

    assert page.count('<i class="d"></i>') == 23
    assert page.count('<i class="s"></i>') == 3
    assert 'role="img" aria-label="26 funções atacadas, 3 com falha grave"' in page
    assert '<div class="grid" ' in page


def test_more_than_sixty_functions_shrink_the_squares_and_two_hundred_become_a_bar() -> None:
    medium = stages_html(view().model_copy(update={"functions": functions(70)}))
    large = stages_html(view().model_copy(update={"functions": functions(201, severe=1)}))

    assert '<div class="grid sm"' in medium
    assert '<div class="grid' not in large
    assert 'class="stack"' in large
    assert 'aria-label="201 funções atacadas, 1 com falha grave"' in large
    assert large.count('<i class="d"></i>') == 0


# ---------------------------------------------------------------- trilho


def test_the_track_has_one_segment_per_stage_with_a_width_proportional_to_the_time() -> None:
    track = render_track(view(), extras=False)

    widths = [float(w) for w in re.findall(r'style="flex: ([0-9.]+) 1 0"', track)]
    assert len(widths) == 5
    assert widths[2] == 1140.0  # a varredura é o trecho mais longo
    assert widths[3] >= 0.1 * sum(w for w in (70.0, 20.0, 1140.0, 2.0))  # nunca some: piso


def test_a_stage_without_a_time_is_not_measured_not_zero() -> None:
    track = render_track(view(summary=None), extras=False)

    assert "não rodou" in track or "— não medido" in track
    assert "0 s" not in track.replace("20 s", "")


# ---------------------------------------------------------------- parou no meio


def partial_view() -> PanelView:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok", duration_seconds=70),
            StageRecord(name="probe", status="ok", duration_seconds=20),
            StageRecord(
                name="scan", status="failed", duration_seconds=600, message="ZAP fora do ar"
            ),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )
    return view(summary=summary)


def test_the_cut_stage_is_yellow_and_the_next_ones_are_grey() -> None:
    page = stages_html(partial_view())

    assert page.count("seg seg-cut") == 1
    assert page.count("seg seg-no") == 2
    assert page.count('class="nb nb-cut"') == 1
    assert page.count('class="nb nb-no"') == 2
    assert "Esta etapa não chegou a rodar." in page
    assert "Parou aqui." in page


def test_the_cut_stage_shows_its_message_as_text_in_a_terminal_block() -> None:
    page = stages_html(partial_view())

    assert '<pre class="term">ZAP fora do ar</pre>' in page
    assert "Mensagem desta etapa:" in page


def test_where_the_test_got_stuck_lists_the_cut_stage_and_the_functions_that_did_not_answer() -> (
    None
):
    text = main_text(stages_html(partial_view()))

    assert "Varredura: parou aqui. ZAP fora do ar" in text
    assert "1 função não respondeu como esperado e não foi atacada." in text


def test_when_nothing_got_stuck_the_panel_says_so() -> None:
    clean = view().model_copy(update={"functions": functions(3)})

    assert "Nada travou: todas as etapas que rodaram terminaram." in main_text(stages_html(clean))


def test_a_skipped_authz_stage_explains_it_is_optional_and_up_to_the_owner() -> None:
    text = main_text(stages_html())

    assert "O teste entre contas é opcional (hdast run --authz) e o dono do produto decide" in text


# ---------------------------------------------------------------- medição


def test_without_metrics_the_rule_panel_says_the_test_predates_the_measurement() -> None:
    page = stages_html()

    assert "— não medido" in page
    assert "este teste é anterior à medição (sem metrics.json)" in page


def test_with_metrics_the_rule_panel_lists_rules_with_alerts_and_counts_the_quiet_ones() -> None:
    base = view()
    measurements = base.measurements.model_copy(
        update={
            "metrics_available": True,
            "rules": (
                rule(40018, "SQL Injection", 2),
                rule(40019, "Path Traversal", 0),
                rule(40020, "Remote Code", 0),
                rule(6, "Slow rule", 0, completed=0, skipped=1),
            ),
        }
    )

    text = main_text(stages_html(base.model_copy(update={"measurements": measurements})))

    assert "SQL Injection 2 alertas" in text
    assert "2 tipos de teste rodaram sem alerta." in text
    assert "1 tipo foi pulado pelo ZAP." in text


def test_tokens_are_not_measured_yet_so_each_stage_says_so() -> None:
    page = stages_html()

    assert page.count("— tokens não medidos") == 5


def test_the_command_diary_adds_a_count_link_per_stage() -> None:
    commands = (
        PanelCommand(command="hdast probe", stage="probe"),
        PanelCommand(command="hdast probe", stage="probe"),
        PanelCommand(command="hdast scan", stage="scan"),
    )

    page = stages_html(view(commands=commands))

    assert '<a href="terminal.html">2 comandos</a>' in page
    assert '<a href="terminal.html">1 comando</a>' in page


@pytest.mark.parametrize("link", ["coverage.html", "time-and-tokens.html", "findings.html"])
def test_the_stage_links_point_to_the_tabs_of_the_panel(link: str) -> None:
    assert f'href="{link}"' in stages_html()


def test_render_stages_is_the_function_of_the_registry() -> None:
    panel_view = view()

    assert render_stages(panel_view) in stages_html(panel_view)
    assert sources().run_id in panel_view.identity.run_id


def preflight_only(status: str = "ready") -> PanelView:
    """Pasta com só a conferência: o `manifest.json` do preflight e nenhum `run.json`."""
    manifest = RunManifest(
        run_id="2026-11-13T23-08-00Z-vampi-7617",
        command="preflight",
        product="vampi",
        harness_version="1.1.0",
        hashes=ArtifactHashes(),
        limits=RunLimits(requests_per_second=1, max_duration_minutes=1, zap_threads_per_host=1),
        seed=0,
        started_at="2026-11-13T23:08:00+00:00",
        status=status,
    )
    return view(
        summary=None, probe=None, scan=None, findings=None, authz=None, metrics=None,
        manifest=manifest,
    )  # fmt: skip


def test_an_error_without_run_json_marks_where_it_stopped_and_never_says_nothing_stuck() -> None:
    panel_view = preflight_only()

    text = main_text(stages_html(panel_view))
    assert panel_view.verdict.kind == "error"
    assert panel_view.verdict.stopped_stage == "probe"
    assert [item.key for item in panel_view.stages if item.state == "cut"] == ["probe"]
    assert "Nada travou" not in text
    assert "Alcance: parou aqui." in text
    assert stages_html(panel_view).count("seg seg-cut") == 1


def test_the_summary_and_the_stages_name_the_same_stage_as_the_one_that_stopped() -> None:
    panel_view = preflight_only()

    summary = main_text(render_panel(panel_view)["summary.html"])
    stages = main_text(stages_html(panel_view))
    assert "O teste deu erro no alcance" in summary
    assert "Alcance: parou aqui." in stages


def test_a_preflight_that_was_not_ready_is_the_stage_that_stopped_and_is_not_green() -> None:
    panel_view = preflight_only("not_ready")

    assert panel_view.verdict.stopped_stage == "preflight"
    assert panel_view.stages[0].state == "cut"
    assert "Conferência: parou aqui." in main_text(stages_html(panel_view))


def test_a_stage_with_a_failure_is_never_drawn_green_in_the_track() -> None:
    page = stages_html(preflight_only("not_ready"))

    assert page.count("seg seg-cut") == 1
    assert page.count('<div class="seg"') == 0
