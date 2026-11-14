"""Casca e componentes do painel: CSP, caminho, menu, marcadores, barras e escape."""

from html.parser import HTMLParser

import pytest

from harness_dast.domain.panel_layout import (
    CSP,
    TabItem,
    bar,
    card,
    chip,
    crumbs,
    document,
    heading,
    marker,
    meter,
    not_measured,
    owner_row,
    render_page,
    row,
    stat,
    tabs_nav,
    terminal,
)
from harness_dast.domain.panel_model import PanelLinks
from tests.unit.domain.panel_helpers import BIDI, XSS, view

TABS = (
    TabItem("summary.html", "Resumo"),
    TabItem("findings.html", "Falhas", 3),
    TabItem("coverage.html", "Cobertura", 0),
)


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.found.append((tag, dict(attrs)))


def parse(page: str) -> list[tuple[str, dict[str, str | None]]]:
    parser = Elements()
    parser.feed(page)
    return parser.found


def page(**changes: object) -> str:
    return render_page(
        view(**changes), current="summary.html", tabs=TABS, title="Resumo", main="<p>x</p>"
    )


def test_the_shell_is_portuguese_blocks_scripts_and_external_loads_and_follows_the_device() -> None:
    html = page()

    assert html.startswith("<!doctype html>")
    assert '<html lang="pt-BR">' in html
    assert f'content="{CSP}"' in html
    assert "default-src 'none'" in html
    assert "script-src" not in html
    assert 'name="viewport"' in html
    assert "prefers-color-scheme: light" in html
    assert "<script" not in html
    assert not any(tag in {"link", "script", "img", "iframe", "form"} for tag, _ in parse(html))


def test_the_current_tab_has_aria_current_page_and_only_it() -> None:
    elements = parse(page())

    current = [attrs for tag, attrs in elements if tag == "a" and attrs.get("aria-current")]
    assert len(current) == 1
    assert current[0]["href"] == "summary.html"
    assert current[0]["aria-current"] == "page"
    assert current[0]["class"] == "on"


def test_the_tab_counter_is_red_when_positive_and_grey_when_zero() -> None:
    html = page()

    assert '<span class="cnt">3</span>' in html
    assert '<span class="cnt" style="background: var(--s2); color: var(--mu)">0</span>' in html


def test_the_path_links_hdast_the_product_and_the_date_with_relative_links() -> None:
    html = page()

    assert 'href="../../index.html">hdast</a>' in html
    assert 'href="../../history-vampi.html">Vampi</a>' in html
    assert "13/11/2026 · 20:08" in html
    assert 'class="here" href="summary.html"' in html


def test_the_path_pieces_are_text_when_the_destination_does_not_exist() -> None:
    html = crumbs("Vampi", "13/11/2026 · 20:08", PanelLinks())

    assert '<span class="crumb">hdast</span>' in html
    assert '<span class="crumb">Vampi</span>' in html
    assert "<a href=" not in html


def test_the_path_escapes_the_product_name_and_the_date() -> None:
    html = crumbs(XSS, XSS, PanelLinks(products="../../index.html", product="../../x.html"))

    assert "<script" not in html
    assert "&lt;script&gt;" in html


def test_a_disabled_tab_is_dimmed_text_never_a_broken_link() -> None:
    html = tabs_nav((TabItem("a.html", "A", enabled=False), TabItem("b.html", "B")), "b.html")

    assert '<span class="off" aria-disabled="true"' in html
    assert 'href="a.html"' not in html
    assert 'aria-current="page"' in html


def test_the_document_has_the_refresh_only_when_asked_and_the_csp_never_changes() -> None:
    with_refresh = document(title="t", header="", main="", refresh_seconds=15)
    without = document(title="t", header="", main="")

    assert '<meta http-equiv="refresh" content="15">' in with_refresh
    assert "refresh" not in without
    assert f'content="{CSP}"' in with_refresh
    assert f'content="{CSP}"' in without


def test_the_header_shows_the_fence_mode_and_the_state_with_the_duration() -> None:
    html = page()

    assert "Cerca: modo estrito" in html
    assert "Terminado · 28 min" in html


def test_the_footer_warns_that_the_page_may_carry_failure_proof() -> None:
    assert "prova de falhas" in page()


def test_the_chip_escapes_text_unless_told_it_is_ours() -> None:
    assert chip("<b>x</b>", "ok") == '<span class="chip ch-ok"><i></i>&lt;b&gt;x&lt;/b&gt;</span>'
    assert chip("ok", "gr", dot=False) == '<span class="chip ch-gr">ok</span>'


@pytest.mark.parametrize(
    ("kind", "spoken"),
    [
        ("ok", "ok: "),
        ("gr", "grave: "),
        ("am", "atenção: "),
        ("run", "agora: "),
        ("out", "proibido: "),
    ],
)
def test_markers_have_their_own_shape_class_and_spoken_text(kind: str, spoken: str) -> None:
    html = marker(kind)  # type: ignore[arg-type]

    assert f'class="dotk k-{kind}"' in html
    assert f'<span class="vh">{spoken}</span>' in html


def test_the_neutral_marker_speaks_nothing() -> None:
    assert marker("no") == '<i class="dotk k-no"></i>'


@pytest.mark.parametrize(
    ("level", "word", "filled"),
    [(1, "a confirmar", 1), (2, "prova forte", 2), (3, "confirmada", 3)],
)
def test_the_meter_has_three_steps_the_word_and_an_aria_label(
    level: int, word: str, filled: int
) -> None:
    html = meter(level)

    assert html.count('<i class="f"></i>') == filled
    assert html.count("<i ") == 3
    assert 'role="img"' in html
    assert f"{word}: degrau {level} de 3" in html
    assert html.endswith(f" {word}")


def test_the_meter_clamps_out_of_range_levels() -> None:
    assert meter(9).count('<i class="f"></i>') == 3
    assert meter(0).count('<i class="f"></i>') == 0


def test_the_stacked_bar_is_an_image_with_the_values_in_the_label() -> None:
    html = bar([(3.0, "ok"), (1.0, "gr"), (0.0, "am")], "3 atacadas, 1 com falha")

    assert 'role="img"' in html
    assert 'aria-label="3 atacadas, 1 com falha"' in html
    assert html.count("<i ") == 2
    assert "width: 75.00%" in html


def test_stat_colours_only_when_the_number_is_a_state() -> None:
    assert 'style="color: var(--gr)"' in stat("3", "falhas graves", tone="gr")
    assert "style=" not in stat("26 de 30", "funções atacadas")


def test_not_measured_is_a_dash_with_the_explanation_never_zero() -> None:
    html = not_measured("teste anterior à medição")

    assert "— não medido" in html
    assert "teste anterior à medição" in html


def test_card_heading_and_rows_are_the_design_blocks() -> None:
    assert card("x", style="flex: 1") == '<section class="card" style="flex: 1">x</section>'
    assert (
        heading("Título", link=("a.html", "ver"))
        == '<h2 class="h">Título <a href="a.html">ver</a></h2>'
    )
    assert 'class="r" style="border-top: 0"' in row("ok", "x", first=True)
    assert owner_row("Você (QA)", "Abrir chamado").startswith(
        '<div class="r"><span class="who">Você (QA)'
    )


def test_the_terminal_block_shows_target_text_only_as_text() -> None:
    html = terminal(f"{XSS}\n{BIDI}\x1b[31m red")

    assert html.startswith('<pre class="term">')
    assert "<script" not in html
    assert "&lt;script&gt;" in html
    assert "‮" not in html
    assert "\x1b" not in html


def test_every_component_escapes_hostile_text() -> None:
    parts = [
        chip(XSS, "gr"),
        stat(XSS, XSS),
        heading(XSS, link=(XSS, XSS)),
        owner_row(XSS, XSS),
        not_measured(XSS),
        bar([(1.0, "ok")], XSS),
        terminal(XSS),
    ]

    for html in parts:
        assert "<script" not in html
        assert "<img" not in html
        assert not any(name.startswith("on") for _, attrs in parse(html) for name in attrs)


def test_a_hostile_tab_label_or_file_cannot_become_markup() -> None:
    html = render_page(view(), current=XSS, tabs=(TabItem(XSS, XSS, 1),), title=XSS, main="")

    assert "<script" not in html
    assert "<title>&lt;script&gt;" in html
    assert not any(name.startswith("on") for _, attrs in parse(html) for name in attrs)
