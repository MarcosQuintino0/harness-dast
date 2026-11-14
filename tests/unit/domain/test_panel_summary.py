"""Aba Resumo: fiel a `screens/summary.html` e aos estados de `system/states.html`."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from harness_dast.domain.panel_model import PanelFinding, PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.panel_summary import render_summary
from harness_dast.domain.run_summary import StageRecord
from harness_dast.domain.traffic import TrafficSummary
from tests.unit.domain.panel_helpers import findings_report, run_summary, sources, view

DESIGN = Path(__file__).parents[3] / "docs" / "design" / "execution-panel" / "screens"
# Classes que a página gerada acrescenta ao HTML da tela: estados que o desenho só descreve em
# texto (`crumb`, `foot`, `seg-cut`, `nb-cut`, `nb-no`) e classes que o CSS do desenho já define
# mas a tela de exemplo não usa (`seg-no`, `vh`, `sm`, `tp`).
EXTRA_CLASSES = {"crumb", "foot", "seg-cut", "nb-cut", "nb-no", "seg-no", "vh", "sm", "tp"}


class Classes(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()
        self.headings: list[str] = []
        self.tabs: list[str] = []
        self._heading: str | None = None
        self._in_tabs = False
        self._in_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "class" and value:
                self.classes.update(value.split())
        self._in_tabs = self._in_tabs or tag == "nav"
        self._in_span = self._in_span or (tag == "span" and self._in_tabs)
        if tag in {"h1", "h2"}:
            self._heading = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_tabs = False
        if tag == "span":
            self._in_span = False
        if tag in {"h1", "h2"} and self._heading is not None:
            self.headings.append(" ".join(self._heading.split()))
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading += data
        if self._in_tabs and not self._in_span and data.strip():
            self.tabs.append(data.strip())


def analyse(page: str) -> Classes:
    parser = Classes()
    parser.feed(page)
    return parser


def summary_html(panel_view: PanelView | None = None) -> str:
    return render_panel(panel_view or view())["summary.html"]


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def with_verdict(panel_view: PanelView, **changes: object) -> PanelView:
    return panel_view.model_copy(update={"verdict": panel_view.verdict.model_copy(update=changes)})


def severe_finding(panel_view: PanelView, index: int, confidence: int, title: str) -> PanelFinding:
    base = panel_view.severe[0]
    return base.model_copy(
        update={"finding_id": f"F-{index:08d}", "confidence": confidence, "title": title}
    )


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = analyse((DESIGN / "summary.html").read_text(encoding="utf-8"))
    generated = analyse(summary_html())

    assert generated.classes <= design.classes | EXTRA_CLASSES


def test_the_page_has_the_main_blocks_and_classes_of_the_design() -> None:
    generated = analyse(summary_html())

    required = {
        "top", "brand", "tabs", "on", "cnt", "chip", "pg", "card", "big", "stats", "stat", "g",
        "h", "r", "dotk", "bars", "who", "track", "seg", "end", "sep", "here", "mu", "sm",
    }  # fmt: skip
    assert required <= generated.classes


def test_the_tabs_and_headings_are_the_ones_of_the_design() -> None:
    generated = analyse(summary_html())

    assert generated.tabs == [
        "Resumo",
        "Etapas",
        "Falhas",
        "Cobertura",
        "Terminal",
        "Tempo e tokens",
    ]
    assert generated.headings[1:] == [
        "Falhas graves Abrir todas",
        "Dá para confiar?",
        "O que fazer agora",
        "As 5 etapas, no tamanho do tempo que levaram Ver os comandos",
    ]


def test_the_block_order_is_hero_three_panels_and_the_stage_track() -> None:
    page = summary_html()

    hero = page.index('class="card" style="padding: 26px 28px"')
    panels = page.index('<div class="g"><section class="card" style="flex: 1.15 1 340px">')
    track = page.index('<div class="track">')
    assert hero < panels < track
    assert page.count('<h1 class="big">') == 1


def test_the_hero_stats_have_the_design_captions() -> None:
    text = main_text(summary_html())

    for caption in ("funções atacadas", "pedidos fora da carta", "do começo ao fim"):
        assert caption in text


# ---------------------------------------------------------------- com falhas graves


@pytest.mark.parametrize(
    ("strong", "weak", "headline"),
    [
        (2, 1, "Duas falhas com prova forte e uma para confirmar."),
        (1, 0, "Uma falha com prova forte."),
        (0, 3, "Três falhas para confirmar."),
        (0, 1, "Uma falha para confirmar."),
        (3, 2, "Três falhas com prova forte e duas para confirmar."),
    ],
)
def test_the_headline_counts_strong_and_to_confirm_failures(
    strong: int, weak: int, headline: str
) -> None:
    page = summary_html(
        with_verdict(view(), strong_count=strong, to_confirm_count=weak, severe_count=strong + weak)
    )

    assert f'<h1 class="big">{headline}</h1>' in page


def test_the_chip_counts_the_severe_failures_and_the_sentence_is_the_fence_clause() -> None:
    page = summary_html()

    assert '<span class="chip ch-gr"><i></i>1 falha grave</span>' in page
    assert "Teste de 13/11/2026. Terminou inteiro." in page
    assert "A cerca não foi medida nesta execução." in page


def test_with_the_fence_measured_the_summary_says_zero_requests_left_the_charter() -> None:
    scan = sources().scan.model_copy(  # type: ignore[union-attr]
        update={"traffic": TrafficSummary(enabled=True, allowed=8203, denied=8651)}
    )

    text = main_text(summary_html(view(scan=scan)))

    assert "Nenhum pedido saiu do combinado na carta." in text
    assert "0 de 16.854 pedidos fora da carta" in text
    assert "0 pedidos fora da carta" in text


def test_requests_outside_the_charter_are_red_and_named() -> None:
    scan = sources().scan.model_copy(  # type: ignore[union-attr]
        update={
            "traffic": TrafficSummary(enabled=True, allowed=10, denied=2, allowed_outside_allow=4)
        }
    )

    page = summary_html(view(scan=scan))

    assert "4 pedidos passaram com leitura fora do combinado" in page
    assert "4 de 12 pedidos fora da carta" in page
    assert '<i class="dotk k-gr"></i><span class="vh">grave: </span><span><b>No agente:</b>' in page


def test_severe_rows_show_the_meter_the_word_and_the_link_to_the_proof() -> None:
    page = summary_html()

    assert 'aria-label="a confirmar: degrau 1 de 3"' in page
    assert "a confirmar" in page
    assert re.search(r'<a class="end" href="findings\.html#F-[0-9a-f]{8}">ver prova</a>', page)
    assert "Ver usuário" in page


def test_more_than_eight_severe_failures_are_grouped_by_cause() -> None:
    panel_view = view()
    many = tuple(severe_finding(panel_view, n, 2, "Comando no banco") for n in range(12))
    many += tuple(severe_finding(panel_view, 100 + n, 1, "Outra coisa") for n in range(2))

    page = summary_html(panel_view.model_copy(update={"severe": many}))

    assert "Comando no banco</b> · 12 funções" in page
    assert "Outra coisa</b> · 2 funções" in page
    assert "abrir o grupo" in page
    assert page.count("ver prova") == 0


def test_the_minor_findings_line_lists_only_what_exists() -> None:
    clean = findings_report(alerts=[])
    base = view().counts
    assert base is not None
    counts = base.model_copy(
        update={"high": 0, "medium": 2, "low": 57, "informational": 31, "groups": 8}
    )

    page = summary_html(view(findings=clean).model_copy(update={"counts": counts}))

    assert (
        "Mais 2 avisos médios, 57 avisos baixos e 31 informativos, agrupados em 8 causas." in page
    )


# ---------------------------------------------------------------- sem falha grave


def test_without_a_severe_failure_the_chip_is_green_and_the_page_is_not_a_certificate() -> None:
    clean = view(findings=findings_report(alerts=[]))

    page = summary_html(clean)

    assert '<span class="chip ch-ok"><i></i>Nenhuma falha grave</span>' in page
    assert "Nenhuma falha grave na única função testada." in page
    assert "Isto não é um atestado de segurança: 4 funções não foram testadas e " in page
    assert "este tipo de teste não vê todo tipo de falha." in page
    assert "Nenhuma falha grave.</b> Veja os avisos menores" in page


def test_the_no_failure_headline_names_how_many_functions_were_tested() -> None:
    clean = with_verdict(view(findings=findings_report(alerts=[])), functions_attacked=26)

    assert "Nenhuma falha grave nas 26 funções testadas." in summary_html(clean)


# ---------------------------------------------------------------- parou no meio e erro


def test_a_partial_run_says_where_it_stopped_how_far_it_got_and_why() -> None:
    summary = run_summary(
        status="interrupted",
        stop_requested=True,
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="interrupted"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )
    partial = with_verdict(view(summary=summary), functions_attacked=11, functions_attempted=26)

    page = summary_html(partial)

    assert '<span class="chip ch-am"><i></i>Parou no meio</span>' in page
    assert "O teste parou na varredura, com 11 de 26 funções atacadas." in page
    assert "Motivo: uma pessoa mandou parar." in page
    assert "O que faltou não foi testado." in page
    assert "Parou no meio · 28 min" in page
    assert "parou no meio, na varredura" in page


def test_a_partial_run_shows_the_reason_the_stage_gave_escaped() -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="failed", message="ZAP <b>fora</b> do ar"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )

    page = summary_html(view(summary=summary))

    assert "Motivo: ZAP &lt;b&gt;fora&lt;/b&gt; do ar." in page


def test_an_error_before_testing_says_nothing_was_attacked_and_what_to_do() -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="failed", message="login recusado"),
            StageRecord(name="probe", status="not_run"),
            StageRecord(name="scan", status="not_run"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )

    page = summary_html(view(summary=summary, probe=None, scan=None, findings=None))

    assert '<span class="chip ch-gr"><i></i>Erro</span>' in page
    assert "O teste deu erro na conferência e nada foi atacado." in page
    assert "Motivo: login recusado." in page
    assert "O que fazer: veja a aba Etapas" in page
    assert "não tem <b>findings.json</b>" in page


# ---------------------------------------------------------------- dado ausente


def test_missing_data_is_a_dash_and_the_words_not_measured_never_zero() -> None:
    page = summary_html(view(summary=None, scan=None, findings=None, probe=None, operations=()))
    text = main_text(page)

    assert "— funções atacadas · não medido" in text
    assert "— pedidos fora da carta · não medido" in text
    assert "— tokens · não medido" in text
    assert "— do começo ao fim" in text or "min do começo ao fim" in text


def test_the_trust_panel_says_when_the_diary_exists_but_has_no_command_of_the_test() -> None:
    text = main_text(render_panel(view(commands=()))["summary.html"])

    assert "o diário existe, mas não tem comando deste teste" in text
    assert "o diário começou na versão 1.2" not in text


def test_the_trust_panel_marks_the_missing_command_diary_and_the_unmeasured_fence() -> None:
    text = main_text(summary_html())

    assert "sem diário de comandos para este teste (o diário começou na versão 1.2)" in text
    assert "pedidos fora da carta não medidos" in text
    assert "nenhuma confirmada por pessoa ainda" in text
    assert "o teste entre contas não rodou" in text


def test_with_the_command_diary_the_trust_panel_counts_and_links_the_terminal() -> None:
    from harness_dast.domain.panel_model import PanelCommand

    commands = tuple(PanelCommand(command=f"hdast v{n}") for n in range(10))

    page = summary_html(view(commands=commands))

    assert "10 comandos, todos visíveis" in page
    assert '<a class="end" href="terminal.html">terminal</a>' in page


def test_the_trust_panel_says_how_many_diary_lines_were_skipped() -> None:
    from harness_dast.domain.panel_model import PanelCommand

    page = summary_html(view(commands=(PanelCommand(command="hdast v"),), commands_skipped=2))

    assert "1 comando, todos visíveis; 2 linhas corrompidas foram puladas" in page


def test_the_next_steps_panel_lists_each_step_with_its_owner() -> None:
    page = summary_html()

    assert 'class="who">Você (QA)' in page
    assert 'class="who">Dono do produto' in page


def test_the_stage_track_shows_the_scan_functions_and_requests() -> None:
    text = main_text(summary_html())

    assert "19 min · 1 função" in text


def test_render_summary_is_the_function_of_the_registry() -> None:
    panel_view = view()

    assert render_summary(panel_view) in summary_html(panel_view)


def test_a_severe_row_is_titled_by_the_function_and_names_the_failure_after_the_meter() -> None:
    page = summary_html()

    assert '<b>Ver usuário</b><br><span class="sm mu"><span class="bars"' in page
    assert re.search(r"a confirmar · SQL Injection</span>", page)


def test_a_severe_row_without_a_function_name_is_titled_by_the_failure() -> None:
    panel_view = view()
    nameless = panel_view.severe[0].model_copy(update={"function_name": None})

    page = summary_html(panel_view.model_copy(update={"severe": (nameless,)}))

    assert "<b>SQL Injection</b><br>" in page
    assert "a confirmar · SQL Injection" not in page


@pytest.mark.parametrize(
    "message", ["Uma pessoa mandou parar.", "Uma pessoa mandou parar", "Parou... "]
)
def test_the_reason_never_ends_in_a_double_period(message: str) -> None:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="failed", message=message),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )

    page = summary_html(view(summary=summary))

    assert ".." not in main_text(page).split("Motivo:")[1].split("O que faltou")[0]
