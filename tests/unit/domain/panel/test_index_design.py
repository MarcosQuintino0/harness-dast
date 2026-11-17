"""Fidelidade ao desenho: produtos, histórico e ao vivo usam as classes e os títulos das telas."""

from pathlib import Path

from harness_dast.domain.panel.index_build import make_entry
from harness_dast.domain.panel.index_pages import render_history, render_products
from harness_dast.domain.panel.live import render_live
from tests.unit.domain.panel.test_index_pages import TODAY, info, run_row, two_products
from tests.unit.domain.panel.test_live import view
from tests.unit.domain.panel.test_summary import EXTRA_CLASSES, analyse

DESIGN = Path(__file__).parents[4] / "docs" / "design" / "execution-panel" / "screens"
"""Classes que o painel acrescenta ao desenho (o desenho não tem a aba desligada, por exemplo)."""
ADDED = EXTRA_CLASSES | {"off", "k-gr", "k-am", "k-ok", "k-no", "k-run", "ch-mu", "here"}


def design(name: str) -> str:
    return (DESIGN / name).read_text(encoding="utf-8")


def starts_like_a_design_heading(heading: str, design_headings: list[str]) -> bool:
    return any(item.startswith(heading) for item in design_headings)


def test_the_products_page_uses_only_design_classes_and_has_the_main_blocks() -> None:
    reference = analyse(design("products.html"))
    generated = analyse(render_products(two_products(), TODAY))

    assert generated.classes <= reference.classes | ADDED
    assert {"top", "brand", "pg", "big", "g", "card", "prod", "nm", "stats", "stat"} <= (
        generated.classes
    )
    assert {"tbl", "scroll", "chip", "dotk"} <= generated.classes


def test_the_products_headings_are_the_ones_of_the_design() -> None:
    reference = analyse(design("products.html"))
    generated = analyse(render_products(two_products(), TODAY))

    assert generated.headings[0] == "Produtos"
    for heading in generated.headings:
        assert starts_like_a_design_heading(heading, reference.headings)


def test_the_history_page_uses_only_design_classes_and_has_the_main_blocks() -> None:
    reference = analyse(design("product-history.html"))
    generated = analyse(render_history(two_products()[0], TODAY))

    assert generated.classes <= reference.classes | ADDED
    assert {"trend", "trendx", "tbl", "selrow", "scroll", "stats", "stat", "r", "end"} <= (
        generated.classes
    )


def test_the_history_headings_are_the_ones_of_the_design_in_the_same_order() -> None:
    reference = analyse(design("product-history.html"))
    generated = analyse(render_history(two_products()[0], TODAY))
    wanted = [item for item in reference.headings if not item.startswith("Clínica")]
    got = [item for item in generated.headings if not item.startswith("Clinica")]

    assert len(got) == len(wanted)
    for heading, original in zip(got, wanted, strict=True):
        assert original.startswith(heading.split(" comparado com")[0])


def test_the_history_with_one_test_drops_the_chart_and_the_comparison_as_states_say() -> None:
    generated = analyse(
        render_history(make_entry("vampi", info(), [run_row("vampi", "13")]), TODAY)
    )

    assert "trend" not in generated.classes
    assert generated.headings[1:] == ["Histórico de testes"]


def test_the_live_page_uses_only_design_classes_and_has_the_main_blocks() -> None:
    reference = analyse(design("live.html"))
    generated = analyse(render_live(view()))

    assert generated.classes <= reference.classes | ADDED
    assert {"track", "seg", "seg-run", "seg-no", "prog", "grid", "lg", "stats", "stat"} <= (
        generated.classes
    )


def test_the_live_menu_has_live_as_the_current_tab_and_the_other_design_tabs_as_text() -> None:
    page = render_live(view())

    assert analyse(page).tabs == ["Ao vivo"]
    for label in ("Resumo", "Falhas", "Cobertura", "Terminal", "Tempo e tokens"):
        assert f">{label}</span>" in page
