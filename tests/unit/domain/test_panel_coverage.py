"""Aba Cobertura: fiel a `screens/coverage.html` e aos estados de `system/states.html`."""

import re
from pathlib import Path

from harness_dast.domain.panel_build import build_panel_view
from harness_dast.domain.panel_coverage import render_coverage
from harness_dast.domain.panel_model import PanelFunction, PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.panel_sources import PanelSources
from tests.unit.domain.panel_helpers import BIDI, XSS, bare, sources, spec_operations, view
from tests.unit.domain.panel_measure_helpers import traffic, with_traffic
from tests.unit.domain.test_panel_pages import markup
from tests.unit.domain.test_panel_summary import EXTRA_CLASSES, analyse, main_text

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "screens"


def coverage_html(panel_view: PanelView | None = None) -> str:
    return render_panel(panel_view or view())["coverage.html"]


def function(state: str, name: str = "Listar", **changes: object) -> PanelFunction:
    base: dict[str, object] = {
        "operation_id": name.lower(),
        "method": "GET",
        "path": f"/{name.lower()}",
        "name": name,
        "area": "Pacientes",
        "state": state,
    }
    base.update(changes)
    return PanelFunction(**base)  # type: ignore[arg-type]


def with_functions(*items: PanelFunction, base: PanelView | None = None) -> PanelView:
    return (base or view()).model_copy(update={"functions": items})


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = analyse((DESIGN / "coverage.html").read_text(encoding="utf-8"))
    generated = analyse(coverage_html(build_panel_view(with_traffic())))

    assert generated.classes <= design.classes | EXTRA_CLASSES | {"cnt", "k-no"}
    assert {"stats", "stack", "area", "fn", "lg", "dotk", "k-ok", "k-gr", "k-am", "k-out"} <= (
        generated.classes
    )
    assert {"b-hatch", "ch-run", "r", "end"} <= generated.classes


def test_the_tab_is_called_cobertura_and_the_headings_follow_the_design() -> None:
    generated = analyse(coverage_html(build_panel_view(with_traffic())))

    assert generated.tabs[3] == "Cobertura"
    assert generated.headings == ["Mapa do sistema", "A cerca modo estrito", "O que ficou de fora"]


def test_the_page_is_no_longer_the_provisional_one() -> None:
    assert "ainda não foi gerada" not in coverage_html()


# ---------------------------------------------------------------- números e mapa


def test_the_numbers_card_counts_functions_by_state() -> None:
    text = main_text(coverage_html())

    assert "5 funções no Swagger" in text
    assert "1 atacadas, com falha grave" in text
    assert "3 não testadas" in text
    assert "1 proibidas pela carta" in text


def test_the_stack_bar_has_a_label_that_says_the_numbers() -> None:
    page = coverage_html()

    assert (
        'role="img" aria-label="0 sem falha grave, 1 com falha grave, 3 não testadas, '
        '1 proibidas"' in page
    )


def test_each_function_has_a_shape_and_a_word_for_screen_readers() -> None:
    panel_view = with_functions(
        function("tested", "Listar pacientes"),
        function("severe", "Buscar paciente", finding_ids=("F-1",)),
        function("failed", "Entrar", reason="Não respondeu."),
        function("not_tried", "Alterar", reason="Não foi tentada."),
        function("forbidden", "Apagar", reason="Função que apaga dados."),
    )

    page = coverage_html(panel_view)

    assert '<i class="dotk k-ok"></i><span class="vh">atacada: </span>Listar pacientes' in page
    assert '<i class="dotk k-gr"></i><span class="vh">com falha grave: </span>' in page
    assert '<i class="dotk k-am"></i><span class="vh">não testada: </span>Entrar' in page
    assert '<i class="dotk k-am"></i><span class="vh">não testada: </span>Alterar' in page
    assert '<i class="dotk k-out"></i><span class="vh">proibida pela carta: </span>' in page
    assert '<span class="fn mu">' in page


def test_a_function_that_was_not_tested_shows_why() -> None:
    panel_view = with_functions(function("failed", "Entrar", reason="Não respondeu no alcance."))

    assert "Entrar Não respondeu no alcance." in main_text(coverage_html(panel_view))


def test_the_reason_of_a_forbidden_function_is_said_once_in_left_out_not_on_every_line() -> None:
    page = coverage_html()

    assert page.count("Função que apaga dados (DELETE): a ferramenta nunca a ataca.") == 1


def test_a_severe_function_links_to_its_anchor_in_the_findings_tab() -> None:
    panel_view = with_functions(
        function("severe", "Buscar paciente", finding_ids=("F-aa11bb22", "F-cc33dd44"))
    )

    page = coverage_html(panel_view)

    assert '<b><a href="findings.html#F-aa11bb22">Buscar paciente</a></b>' in page
    assert 'href="findings.html#F-cc33dd44">prova 2</a>' in page


def test_the_anchor_is_the_same_the_summary_tab_uses() -> None:
    pages = render_panel(view())
    finding_id = view().severe[0].finding_id

    assert f'href="findings.html#{finding_id}"' in pages["summary.html"]
    assert f'href="findings.html#{finding_id}"' in pages["coverage.html"]


def test_functions_are_grouped_by_area_with_attacked_of_total() -> None:
    panel_view = with_functions(
        function("tested", "A", area="Pacientes"),
        function("forbidden", "B", area="Pacientes"),
        function("tested", "C", area="Médicos"),
    )

    page = coverage_html(panel_view)

    assert "<h3>Pacientes <span>1 de 2</span></h3>" in page
    assert "<h3>Médicos <span>1 de 1</span></h3>" in page
    assert page.index("Pacientes") < page.index("Médicos")


def test_the_real_scenario_groups_the_open_api_tag_and_the_others() -> None:
    page = coverage_html()

    assert "<h3>Usuários <span>1 de 1</span></h3>" in page
    assert "<h3>Outras <span>0 de 4</span></h3>" in page


def test_the_legend_has_the_four_states_of_the_design() -> None:
    text = main_text(coverage_html())

    for label in (
        "atacada, sem falha grave",
        "atacada, com falha grave",
        "não testada",
        "proibida pela carta",
    ):
        assert label in text


def test_without_any_function_the_map_says_not_measured_not_zero() -> None:
    page = render_panel(build_panel_view(bare()))["coverage.html"]
    text = main_text(page)

    assert "— não medido" in text
    assert "0 funções" not in text


def test_render_is_a_pure_function_of_the_view() -> None:
    panel_view = view()

    assert render_coverage(panel_view) == render_coverage(panel_view)


# ---------------------------------------------------------------- o que ficou de fora


def test_left_out_lists_risk_and_who_unlocks_each_item() -> None:
    text = main_text(coverage_html())

    assert "Uma conta vendo dados de outra." in text
    assert "Risco: falha de autorização pode existir sem ter sido vista." in text
    assert "Destrava: o dono do produto autoriza o teste entre contas na carta." in text
    assert "Destrava: pedir ao agente para melhorar o alcance" in text
    assert "Destrava: só o dono do produto, pela carta." in text
    assert "Destrava: repetir o teste até a varredura chegar a elas." in text


def test_the_blind_spots_of_this_kind_of_test_are_always_listed() -> None:
    text = main_text(coverage_html())

    assert "não vê falha de lógica de negócio" in text
    assert "Sem falha grave não é atestado" in text


def test_when_everything_was_tested_the_card_says_nothing_was_left_out() -> None:
    panel_view = with_functions(function("tested"), function("tested", "Ver"))
    panel_view = panel_view.model_copy(
        update={"left_out": tuple(item for item in view().left_out if item.kind == "blind")}
    )

    text = main_text(coverage_html(panel_view))

    assert "Nada ficou de fora dentro do que a carta permite." in text
    assert "Sem falha grave não é atestado" in text
    assert "Destrava" not in text


def test_the_page_never_says_safe_or_approved() -> None:
    text = main_text(coverage_html(build_panel_view(with_traffic()))).lower()

    assert "seguro" not in text.replace("atestado de segurança", "")
    assert "aprovado" not in text


# ---------------------------------------------------------------- a cerca


def test_the_fence_shows_passed_and_barred_with_the_real_numbers() -> None:
    text = main_text(coverage_html(build_panel_view(with_traffic())))

    assert "Dos 16.854 que o teste tentou mandar" in text
    assert "Passaram e chegaram ao sistema 8.203" in text
    assert "Barrados: endereço disfarçado 7.538" in text
    assert "Barrados: apontavam para fora 1.113" in text
    assert "Chegaram a lugar proibido 0" in text
    assert "modo estrito" in text


def test_the_fence_bar_says_the_numbers_for_a_screen_reader() -> None:
    page = coverage_html(build_panel_view(with_traffic()))

    assert (
        'aria-label="8.203 passaram, 7.538 barrados pela forma do endereço, 1.113 barrados por '
        'apontar para fora ou por outro motivo"' in page
    )
    assert 'class="b-hatch"' in page


def test_the_reasons_come_with_the_plain_name_and_the_code() -> None:
    text = main_text(coverage_html(build_panel_view(with_traffic())))

    assert "barra codificada no caminho (%2f) [path_encoded_slash] 2.608" in text
    assert "caminho fora do que a carta permite (scope.allow) [path_not_allowed] 1.087" in text
    assert "e mais 1 motivos menores." in text


def test_the_partial_coverage_notice_appears_when_the_shape_of_the_path_blocked_requests() -> None:
    text = main_text(coverage_html(build_panel_view(with_traffic())))

    assert "Cobertura parcial." in text
    assert "7.538 de 16.854 pedidos foram barrados pela forma do endereço" in text
    assert "Só o dono do produto pode autorizar o modo amplo na carta" in text
    assert "Ataques por endereço disfarçado." in text


def test_no_partial_notice_when_nothing_was_barred_by_shape() -> None:
    quiet = with_traffic(denied=0, denied_by_reason={}, denied_by_detail={}, path_shape_denied=0)

    text = main_text(coverage_html(build_panel_view(quiet)))

    assert "Cobertura parcial" not in text
    assert "Ataques por endereço disfarçado" not in text


def test_the_fence_explains_strict_and_wide_in_one_sentence() -> None:
    text = main_text(coverage_html(build_panel_view(with_traffic())))

    assert "Modo estrito: só passa endereço escrito de forma simples" in text
    assert "Modo amplo (só se a carta autorizar)" in text


def test_wide_mode_changes_the_chip_the_row_and_drops_the_disguised_address_item() -> None:
    wide = with_traffic(path_mode="wide", allowed_outside_allow=12)
    panel_view = build_panel_view(wide).model_copy(
        update={"identity": view().identity.model_copy(update={"fence_mode": "wide"})}
    )

    text = main_text(coverage_html(panel_view))

    assert "A cerca modo amplo" in text
    assert "Endereço disfarçado: decifrados e passaram 12" in text
    assert "Chegaram a lugar proibido" not in text
    assert "Ataques por endereço disfarçado" not in text


def test_traffic_without_the_proxy_audit_is_a_dash_with_the_explanation_never_zero() -> None:
    scan = sources().scan.model_copy(update={"traffic": traffic(enabled=False)})  # type: ignore[union-attr]
    panel_view = build_panel_view(sources(scan=scan))

    text = main_text(coverage_html(panel_view))

    assert "— não medido sem a auditoria do proxy" in text
    assert "Pedidos barrados —" in text
    assert "Passaram e chegaram" not in text


def test_without_scan_the_fence_says_it_was_not_measured() -> None:
    text = main_text(coverage_html(build_panel_view(sources(scan=None))))

    assert "— não medido a cerca não foi medida" in text


def test_an_old_scan_without_the_granular_codes_still_splits_the_barred_requests() -> None:
    old = with_traffic(denied_by_detail={}, path_shape_denied=7538)

    text = main_text(coverage_html(build_panel_view(old)))

    assert "Barrados: endereço disfarçado 7.538" in text
    assert "Barrados: apontavam para fora 1.113" in text


def test_barred_requests_with_an_unknown_reason_go_to_other_reasons() -> None:
    odd = with_traffic(
        denied=100,
        denied_by_reason={"kill_switch": 100},
        denied_by_detail={"kill_switch": 100},
        path_shape_denied=0,
        allowed=900,
    )

    text = main_text(coverage_html(build_panel_view(odd)))

    assert "Barrados: outros motivos 100" in text
    assert "parada de emergência acionada [kill_switch] 100" in text


# ---------------------------------------------------------------- texto hostil


def hostile_view() -> PanelView:
    scan = sources().scan.model_copy(  # type: ignore[union-attr]
        update={
            "traffic": traffic(
                denied_by_detail={f"{XSS}{BIDI}": 5},
                denied_by_reason={f"{XSS}{BIDI}": 5},
                denied=5,
            )
        }
    )
    source: PanelSources = sources(
        scan=scan, operations=spec_operations(summary=f"{XSS}{BIDI}", tag=XSS)
    )
    return build_panel_view(source).model_copy(
        update={
            "functions": (
                function("severe", f"{XSS}{BIDI}", area=XSS, finding_ids=('F-"><script>',)),
                function("failed", XSS, area=XSS, reason=None),
            )
        }
    )


def test_hostile_text_is_escaped_in_names_areas_ids_and_reasons() -> None:
    page = coverage_html(hostile_view())

    parsed = markup(page)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags
    assert not any(name.startswith("on") for name, _ in parsed.attributes)
    assert "‮" not in page
    assert 'href="findings.html#F-&quot;&gt;&lt;script&gt;"' in page
    assert re.search(r"<h3>&lt;script&gt;alert\(1\)&lt;/script&gt;", page)
