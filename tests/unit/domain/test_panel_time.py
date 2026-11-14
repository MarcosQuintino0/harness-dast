"""Aba Tempo e tokens: fiel a `screens/time-and-tokens.html` e ao estado "teste sem medição"."""

import re
from pathlib import Path

from harness_dast.domain.panel_model import PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.panel_time import render_time
from harness_dast.domain.rule_stats import RuleStat
from harness_dast.domain.run_metrics import OperationMetric
from tests.unit.domain.panel_helpers import BIDI, XSS, view
from tests.unit.domain.panel_measure_helpers import (
    agent_metrics,
    measured_view,
    rule_total,
    run_metrics,
)
from tests.unit.domain.test_panel_pages import markup
from tests.unit.domain.test_panel_summary import EXTRA_CLASSES, analyse, main_text

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "screens"


def time_html(panel_view: PanelView | None = None) -> str:
    return render_panel(panel_view or measured_view())["time-and-tokens.html"]


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = analyse((DESIGN / "time-and-tokens.html").read_text(encoding="utf-8"))
    generated = analyse(time_html())

    assert generated.classes <= design.classes | EXTRA_CLASSES | {
        "cnt",
        "k-no",
        "k-am",
        "dotk",
        "end",
    }
    assert {"stats", "stat", "cost", "cb", "tk", "r", "card", "g"} <= generated.classes


def test_the_tab_is_called_tempo_e_tokens_and_the_headings_follow_the_design() -> None:
    generated = analyse(time_html())

    assert generated.tabs[5] == "Tempo e tokens"
    assert generated.headings[:5] == [
        "Por etapa",
        "Tokens do agente modelo claude-sonnet-5-5",
        "Tipos de teste que mais demoraram",
        "Funções que mais demoraram",
        "Lacunas sem tráfego",
    ]
    assert generated.headings[-1] == "Regras desligadas"


def test_the_page_is_no_longer_the_provisional_one() -> None:
    assert "ainda não foi gerada" not in time_html()


def test_render_is_a_pure_function_of_the_view() -> None:
    panel_view = measured_view()

    assert render_time(panel_view) == render_time(panel_view)


# ---------------------------------------------------------------- números em destaque


def test_the_top_numbers_come_from_the_run() -> None:
    text = main_text(time_html())

    assert "28 min do começo ao fim" in text
    assert "168 mil tokens (trabalho do agente de IA)" in text
    assert "19 min só de varredura (68% do tempo)" in text
    assert "1 funções atacadas" in text


def test_traffic_not_measured_is_a_dash_with_the_explanation() -> None:
    assert "— pedidos de ataque tentados · não medido" in main_text(time_html())


# ---------------------------------------------------------------- por etapa


def test_the_stage_table_has_time_and_tokens_for_each_stage() -> None:
    text = main_text(time_html())

    assert "1 · Conferência 1 min 111 mil" in text
    assert "2 · Alcance 20 s 12 mil" in text
    assert "3 · Varredura 19 min 17 mil" in text
    assert "5 · Achados 2 s 25 mil" in text
    assert "Total 28 min 168 mil" in text


def test_a_stage_measured_in_a_fraction_of_a_second_is_never_shown_as_zero() -> None:
    panel_view = measured_view()
    stages = tuple(
        item.model_copy(update={"seconds": 0.079}) if item.key == "report" else item
        for item in panel_view.stages
    )

    text = main_text(time_html(panel_view.model_copy(update={"stages": stages})))

    assert "5 · Achados menos de 1 s" in text
    assert not re.search(r"(?<![0-9])0 s", text)


def test_a_stage_that_did_not_run_says_so_and_has_no_bar() -> None:
    text = main_text(time_html())

    assert "4 · Entre contas não rodou" in text


def test_tokens_of_the_agent_that_belong_to_no_stage_get_their_own_row() -> None:
    assert "Outras tarefas do agente — 3 mil" in main_text(time_html())


def test_every_bar_is_an_image_with_a_label_in_words() -> None:
    page = time_html()
    bars = re.findall(r'<i[^>]*role="img"[^>]*aria-label="([^"]+)"', page)

    assert len(bars) >= 8
    assert "Varredura: 19 min, 68% do tempo" in bars
    assert any(label.startswith("Varredura: 17 mil tokens") for label in bars)
    assert 'class="tk" role="img"' in page


def test_the_reading_sentence_comes_from_the_numbers_of_the_run() -> None:
    text = main_text(time_html())

    assert "A maior parte do tempo foi da etapa Varredura" in text
    assert "A maior parte dos tokens foi da etapa Conferência (66% dos tokens medidos)." in text


# ---------------------------------------------------------------- tokens


def test_the_tokens_card_shows_the_model_and_the_split_and_says_the_cache_read_is_not_summed() -> (
    None
):
    text = main_text(time_html())

    assert "modelo claude-sonnet-5-5" in text
    assert "Entrada 82 Saída 19 mil Entrada gravada no cache 149 mil" in text
    assert "Entrada relida do cache 4,5 mi · não entra na soma" in text


def test_without_the_agent_file_tokens_are_a_dash_with_the_explanation_never_zero() -> None:
    page = time_html(view(metrics=run_metrics()))
    text = main_text(page)

    assert "— tokens · não medido" in text
    assert "a CLI não mede os tokens" in text
    assert "agent-metrics.json" in text
    assert "0 tokens" not in text
    assert page.count("— não medido</span>") >= 4


def test_a_tolerant_file_without_totals_still_shows_the_stage_tokens() -> None:
    panel_view = measured_view(agent_metrics=agent_metrics(totals=None))

    text = main_text(time_html(panel_view))

    assert "— tokens · não medido" in text
    assert "2 · Alcance 20 s 12 mil" in text


# ---------------------------------------------------------------- regras, funções, lacunas


def test_the_slowest_rules_come_first_with_requests_and_a_full_bar_legend() -> None:
    text = main_text(time_html())

    assert "SQL Injection 63 pedidos 6 s" in text
    assert "Path Traversal 63 pedidos menos de 1 s" in text
    assert text.index("SQL Injection") < text.index("Path Traversal")
    assert "Barra cheia = 6 s neste quadro." in text


def test_a_rule_with_no_time_is_not_listed_among_the_slowest() -> None:
    top = main_text(time_html()).split("Funções que mais demoraram")[0]
    top = top.split("Tipos de teste que mais demoraram")[1].split("Puladas")[0]

    assert "Remote OS Command Injection" not in top


def test_skipped_and_interrupted_rules_say_why() -> None:
    text = main_text(time_html())

    assert (
        "Remote OS Command Injection pulada: passou do tempo máximo que cada tipo de teste pode "
        "gastar (1 varredura)" in text
    )
    assert "Path Traversal interrompida: ainda rodava quando a varredura terminou" in text


def test_a_skip_without_a_known_reason_does_not_invent_one() -> None:
    operation = OperationMetric(
        operation_id="obter",
        outcome="completed",
        duration_seconds=3.0,
        requests=5,
        rules_available=True,
        rules=(RuleStat(plugin_id=1, name="X", state="skipped", skip_reason="coisa-nova"),),
    )

    text = main_text(time_html(measured_view(metrics=run_metrics(operations=(operation,)))))

    assert "X pulada: o ZAP não disse o motivo" in text


def test_the_unmeasured_scans_are_admitted_in_the_rule_card() -> None:
    assert "A soma cobre 1 de 2 varreduras; as outras ficaram sem a medição" in main_text(
        time_html()
    )


def test_functions_use_the_simple_name_and_show_the_slowest_first() -> None:
    text = main_text(time_html())

    assert "Ver usuário 120 pedidos 56 s" in text
    assert text.index("Ver usuário") < text.index("listar 40 pedidos")
    assert "Barra cheia = 56 s neste quadro." in text


def test_gaps_are_counted_and_explained() -> None:
    text = main_text(time_html())

    assert "2 lacunas de mais de 10 s" in text
    assert "somando 49 s; a maior durou 30 s." in text
    assert "nenhum pedido passou pela cerca" in text


def test_no_gaps_is_said_in_words() -> None:
    from harness_dast.domain.run_metrics import TrafficMetrics
    from harness_dast.domain.traffic import TrafficGaps

    metrics = run_metrics(traffic=TrafficMetrics(available=True, gaps=TrafficGaps(count=0)))

    assert "Nenhuma lacuna: o tráfego nunca ficou parado por mais de 10 s." in main_text(
        time_html(measured_view(metrics=metrics))
    )


def test_gaps_without_the_proxy_audit_are_a_dash_not_zero() -> None:
    from harness_dast.domain.run_metrics import TrafficMetrics

    metrics = run_metrics(traffic=TrafficMetrics(available=False, gaps=None))

    text = main_text(time_html(measured_view(metrics=metrics)))

    assert "— não medido sem a auditoria do proxy não há como medir" in text


def test_disabled_rules_show_the_reason_and_who_disabled_them() -> None:
    text = main_text(time_html())

    assert "Buffer Overflow Destrutiva. da ferramenta" in text
    assert "regra 99 Pedido do perfil. do perfil" in text


def test_a_run_with_no_disabled_rules_says_so() -> None:
    text = main_text(time_html(measured_view(metrics=run_metrics(disabled_rules=()))))

    assert "Nenhuma regra desligada." in text


# ---------------------------------------------------------------- teste antigo, sem metrics.json


def test_a_run_without_metrics_json_is_dashes_with_the_explanation_in_every_card() -> None:
    page = time_html(view())
    text = main_text(page)

    assert text.count("este teste é anterior à medição (sem metrics.json)") == 4
    assert "Barra cheia" not in text
    assert "28 min do começo ao fim" in text


def test_metrics_without_rule_times_say_so() -> None:
    metrics = run_metrics(rules=run_metrics().rules.model_copy(update={"totals": ()}))

    text = main_text(time_html(measured_view(metrics=metrics)))

    assert "o ZAP não informou o tempo por tipo de teste nesta execução" in text


def test_every_rule_with_zero_time_is_not_shown_as_a_slow_rule() -> None:
    metrics = run_metrics(
        rules=run_metrics().rules.model_copy(update={"totals": (rule_total(1, "A", 0),)})
    )

    assert "o ZAP não informou o tempo" in main_text(time_html(measured_view(metrics=metrics)))


# ---------------------------------------------------------------- texto hostil


def test_hostile_rule_names_functions_and_model_are_escaped() -> None:
    hostile_rule = rule_total(7, f"{XSS}{BIDI}", 5000)
    metrics = run_metrics(
        rules=run_metrics().rules.model_copy(update={"totals": (hostile_rule,)}),
        disabled_rules=(
            run_metrics()
            .disabled_rules[0]
            .model_copy(update={"name": XSS, "reason": f"{XSS}{BIDI}"}),
        ),
    )
    agent = agent_metrics(model=XSS)

    page = time_html(measured_view(metrics=metrics, agent_metrics=agent))

    parsed = markup(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert not any(name.startswith("on") for name, _ in parsed.attributes)
    assert "‮" not in page
    assert "&lt;script&gt;" in page
