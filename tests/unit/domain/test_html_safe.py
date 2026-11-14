"""Escape de HTML do painel: o texto do alvo nunca vira marcação; o código nosso vira etiqueta."""

import re

from harness_dast.domain import html_safe as h
from harness_dast.domain.api_model import Operation
from harness_dast.domain.panel_build import build_panel_view
from harness_dast.domain.panel_build_content import function_names
from harness_dast.domain.panel_model import PanelFunction
from harness_dast.domain.panel_pages import render_panel
from tests.unit.domain.panel_helpers import sources


def test_tagged_turns_backticked_code_into_a_grey_chip_and_keeps_the_rest_escaped() -> None:
    got = h.tagged("Caminho que a carta proíbe, na lista `deny_paths`. <b>x</b>")

    assert got == (
        'Caminho que a carta proíbe, na lista <span class="chip ch-mu">deny_paths</span>. '
        "&lt;b&gt;x&lt;/b&gt;"
    )


def test_tagged_never_lets_markup_inside_the_backticks_through() -> None:
    got = h.tagged("`<script>alert(1)</script>`")

    assert "<script>" not in got
    assert "chip" not in got


def test_tagged_leaves_an_unbalanced_backtick_alone() -> None:
    assert h.tagged("um ` solto") == "um ` solto"


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def test_functions_with_the_same_summary_are_told_apart_by_method_and_path() -> None:
    operations = (
        Operation(operation_id="a", method="get", path="/api/x/1", summary="Isca de avaliação"),
        Operation(operation_id="b", method="get", path="/api/x/2", summary="Isca de avaliação"),
        Operation(operation_id="c", method="get", path="/api/y", summary="Lista y"),
    )

    names = function_names(operations)

    assert names["a"] == "Isca de avaliação (GET /api/x/1)"
    assert names["b"] == "Isca de avaliação (GET /api/x/2)"
    assert names["c"] == "Lista y"


def test_the_coverage_page_has_the_reason_in_plain_words_and_the_code_in_a_grey_chip() -> None:
    base = build_panel_view(sources())
    forbidden = PanelFunction(
        operation_id="isca",
        method="GET",
        path="/api/x",
        name="Apaga tudo",
        area="Outras",
        state="forbidden",
        reason="Caminho que a carta proíbe, na lista `deny_paths`.",
    )
    view = base.model_copy(update={"functions": (*base.functions, forbidden)})
    page = render_panel(view)["coverage.html"]

    assert "(deny_paths)" not in page
    assert page.count('<span class="chip ch-mu">deny_paths</span>') >= 1
    assert "`" not in page
    assert "Caminho que a carta proíbe, na lista" in main_text(page)
