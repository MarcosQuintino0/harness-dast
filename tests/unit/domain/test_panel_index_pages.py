"""Páginas dos índices: produtos e histórico, estados, texto hostil e links que existem."""

import re
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser

from harness_dast.domain.panel_index_build import make_entry
from harness_dast.domain.panel_index_model import ProductEntry, ProductInfo, RowFinding, RunRow
from harness_dast.domain.panel_index_pages import render_history, render_products
from tests.unit.domain.panel_helpers import BIDI, XSS

TODAY = date(2026, 11, 14)
SAFE_ATTRIBUTES = {
    "class", "href", "style", "lang", "charset", "name", "content", "http-equiv", "role",
    "aria-label", "title",
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


def run_row(
    product: str,
    stamp: str,
    ids: tuple[str, ...] | None = ("F-1",),
    *,
    hour: int = 20,
    verdict: str = "finished",
    panel: bool = True,
    kind: str = "scan",
    what: str = "Varredura completa",
) -> RunRow:
    run_id = f"2026-11-{stamp}T{hour:02d}-08-00Z-{product}-ab12"
    return RunRow(
        run_id=run_id,
        product=product,
        state="ok",
        started_at=datetime(2026, 11, int(stamp), hour, 8, tzinfo=UTC),
        kind=kind,  # type: ignore[arg-type]
        what_ran=what,
        verdict=verdict,  # type: ignore[arg-type]
        functions_attacked=26,
        functions_basis=30,
        functions_total=40,
        severe_count=None if ids is None else len(ids),
        severe=tuple(RowFinding(finding_id=item, title=f"falha {item}") for item in ids or ()),
        duration_seconds=1680.0,
        fence_mode="strict",
        panel_link=f"{run_id}/panel/summary.html" if panel else None,
    )


def info(valid_until: date | None = date(2026, 11, 30)) -> ProductInfo:
    return ProductInfo(
        profile_available=True,
        authorization_reference="LAB-CLINICA",
        valid_until=valid_until,
        fence_mode="strict",
    )


def two_products() -> list[ProductEntry]:
    clinic = make_entry(
        "clinica-piloto",
        info(),
        [
            run_row("clinica-piloto", "12", ("F-1",), hour=9),
            run_row("clinica-piloto", "13", ("F-1", "F-2"), hour=8),
            run_row("clinica-piloto", "13", ("F-2", "F-3", "F-4"), hour=20),
        ],
    )
    vampi = make_entry("vampi", info(date(2026, 11, 16)), [run_row("vampi", "13", (), hour=16)])
    return [clinic, vampi]


def visible(page: str) -> str:
    return re.sub(r"<style>.*?</style>", "", page, flags=re.S)


def test_the_products_page_has_a_card_per_product_and_the_last_tests_table() -> None:
    page = render_products(two_products(), TODAY)

    assert "<h1" in page
    assert "Produtos" in page
    assert "2 produtos testados · 4 testes feitos" in page
    assert page.count('class="card prod"') == 2
    assert "Clinica Piloto" in page
    assert "Vampi" in page
    assert "3 falhas graves abertas" in page
    assert "Nenhuma falha grave no último relatório" in page
    assert "Últimos testes, de todos os produtos" in page
    assert "Testar um produto novo" in page
    assert "Página gerada pelo hdast · 14/11/2026" in page


def test_the_card_says_when_the_letter_is_valid_expiring_expired_or_unknown() -> None:
    valid = render_products(
        [make_entry("a", info(date(2026, 12, 31)), [run_row("a", "13")])], TODAY
    )
    soon = render_products([make_entry("a", info(date(2026, 11, 16)), [run_row("a", "13")])], TODAY)
    last_day = render_products([make_entry("a", info(TODAY), [run_row("a", "13")])], TODAY)
    expired = render_products(
        [make_entry("a", info(date(2026, 11, 1)), [run_row("a", "13")])], TODAY
    )
    unknown = render_products([make_entry("a", ProductInfo(), [run_row("a", "13")])], TODAY)

    assert "válida até 31/12/2026" in valid
    assert "k-ok" in valid
    assert "vence em 2 dias" in soon
    assert "k-am" in soon
    assert "vence hoje" in last_day
    assert "venceu em 01/11/2026" in expired
    assert "k-gr" in expired
    assert "Carta não consultada" in unknown
    assert "cerca no modo estrito" in valid


def test_with_no_product_the_page_shows_only_the_empty_card_and_no_table() -> None:
    page = render_products([], TODAY)

    assert "Nenhum produto testado ainda" in page
    assert "nenhum produto testado ainda" in page
    assert "<table" not in page
    assert "Testar um produto novo" not in page


def test_a_card_for_one_test_uses_the_singular() -> None:
    page = render_products([make_entry("vampi", info(), [run_row("vampi", "13")])], TODAY)

    assert "1 produto testado · 1 teste feito" in page
    assert "<span>teste feito</span>" in page


def test_a_run_without_a_panel_shows_the_date_as_text_with_a_notice() -> None:
    entry = make_entry("vampi", info(), [run_row("vampi", "13", panel=False)])

    page = render_products([entry], TODAY)

    assert "sem painel" in page
    assert "/panel/summary.html" not in page


def test_unreadable_and_error_runs_show_up_as_honest_rows() -> None:
    rows = [
        RunRow(run_id="2026-11-13T20-08-00Z-vampi-ab12", product="vampi", state="empty"),
        run_row("vampi", "12", None, verdict="error", what="Só conferência", kind="preflight"),
        run_row("vampi", "11", ("F-1",), hour=7).model_copy(update={"state": "partial"}),
    ]

    page = render_history(make_entry("vampi", info(), rows), TODAY)

    assert "sem dados" in page
    assert "erro" in page
    assert "dados incompletos" in page
    assert page.count("<tr") == 4


def test_the_history_with_one_test_has_no_chart_no_comparison_and_says_first_time() -> None:
    page = render_history(make_entry("vampi", info(), [run_row("vampi", "13")]), TODAY)

    assert "primeira vez" in page
    assert 'class="trend"' not in page
    assert "Desde a varredura anterior" not in page
    assert "Falhas abertas há mais tempo" not in page
    assert "Histórico de testes" in page


def test_the_history_with_several_tests_shows_chart_comparison_and_oldest() -> None:
    clinic = two_products()[0]

    page = render_history(clinic, TODAY)

    assert 'class="trend"' in page
    assert 'aria-label="Falhas graves por varredura: 1, depois 2, depois 3"' in page
    assert "Desde a varredura anterior" in page
    assert "1 não apareceu" in page
    assert "1 continua" in page
    assert "2 novas" in page
    assert "Falhas abertas há mais tempo" in page
    assert "2 novas · 1 continua · 1 não apareceu" in page
    assert "primeira vez" in page
    assert "<b>3</b>" in page or 'color: var(--gr)">3</b>' in page


def test_the_chart_is_white_not_red() -> None:
    page = render_history(two_products()[0], TODAY)

    assert ".trend i{display:block;width:100%;max-width:44px;background:var(--ink)" in page


def test_the_latest_row_is_marked_and_dates_link_to_the_test_summary() -> None:
    page = render_history(two_products()[0], TODAY)

    assert page.count('class="selrow"') == 1
    assert 'href="2026-11-13T20-08-00Z-clinica-piloto-ab12/panel/summary.html"' in page


def test_the_history_top_card_sums_time_and_shows_tokens_as_not_measured() -> None:
    page = render_history(two_products()[0], TODAY)

    assert "testes feitos" in page
    assert "1 h 24" in page
    assert 'title="não medido"' in page


def test_every_link_goes_to_a_page_that_exists_and_is_relative() -> None:
    entries = two_products()
    existing = {"index.html"} | {f"history-{item.product}.html" for item in entries}
    existing |= {row.panel_link for item in entries for row in item.rows if row.panel_link}

    pages = [render_products(entries, TODAY)] + [render_history(item, TODAY) for item in entries]

    for page in pages:
        for link in markup(page).links:
            assert link in existing, link
            assert not link.startswith(("/", "http"))


def test_no_index_page_has_script_external_resource_or_event_handler() -> None:
    entries = two_products()
    pages = [render_products(entries, TODAY)] + [render_history(item, TODAY) for item in entries]

    for page in pages:
        parsed = markup(page)
        assert "<script" not in page.lower()
        assert not FORBIDDEN_TAGS & set(parsed.tags)
        assert not re.search(r"https?://", page)
        assert "onclick" not in page.lower()
        assert {key for key, _ in parsed.attributes} <= SAFE_ATTRIBUTES
        assert 'lang="pt-BR"' in page
        assert "default-src 'none'" in page


def test_the_pages_never_say_safe_or_approved() -> None:
    entries = two_products()
    for page in [render_products(entries, TODAY), render_history(entries[1], TODAY)]:
        assert not re.search(r"\b(seguro|segura|aprovad[oa])\b", visible(page), flags=re.I)


def test_hostile_text_from_the_profile_and_the_findings_is_escaped() -> None:
    hostile = ProductInfo(
        profile_available=True,
        authorization_reference=f"{XSS}{BIDI}",
        valid_until=date(2026, 12, 31),
    )
    rows = [
        run_row("vampi", "12", (XSS,)).model_copy(
            update={"severe": (RowFinding(finding_id=XSS, title=f"{XSS}{BIDI}"),)}
        ),
        run_row("vampi", "13", ()).model_copy(update={"what_ran": XSS}),
    ]
    entry = make_entry("vampi", hostile, rows)

    for page in (render_products([entry], TODAY), render_history(entry, TODAY)):
        assert "<script" not in page
        assert "<img" not in page
        assert "‮" not in page
        assert not any(key.startswith("on") for key, _ in markup(page).attributes)
        assert "&lt;script&gt;" in page


def test_the_chart_height_never_overflows_and_zero_is_still_drawn() -> None:
    rows = [
        run_row("vampi", "12", ("F-1", "F-2", "F-3", "F-4"), hour=9),
        run_row("vampi", "13", (), hour=9),
    ]

    page = render_history(make_entry("vampi", info(), rows), TODAY)

    assert 'style="height: 70px"' in page
    assert 'style="height: 0px"' in page


def test_a_card_without_findings_report_says_so() -> None:
    page = render_products([make_entry("vampi", info(), [run_row("vampi", "13", None)])], TODAY)

    assert "sem relatório de falhas" in page


def test_dates_use_the_zone_the_row_already_carries() -> None:
    zone = UTC
    row = run_row("vampi", "13", hour=20).model_copy(
        update={"started_at": datetime(2026, 11, 13, 20, 8, tzinfo=zone) - timedelta(hours=3)}
    )

    assert "13/11/2026 · 17:08" in render_products([make_entry("vampi", info(), [row])], TODAY)


def test_a_newer_test_without_a_report_does_not_erase_the_open_failures() -> None:
    rows = [
        run_row("vampi", "14", None, verdict="error", what="Só conferência", kind="preflight"),
        run_row("vampi", "13", ("F-1", "F-2")),
    ]

    page = render_products([make_entry("vampi", info(), rows)], TODAY)

    assert "2 falhas graves abertas" in page
