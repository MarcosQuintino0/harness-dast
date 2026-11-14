"""Página "Ao vivo": recarga só durante o teste, estados, menu e texto hostil."""

import re
from datetime import UTC, datetime
from html.parser import HTMLParser

from harness_dast.domain.panel_layout import CSP
from harness_dast.domain.panel_live import REFRESH_SECONDS, render_live
from harness_dast.domain.panel_live_model import LivePhase, LiveStage, LiveStageState, LiveView
from harness_dast.domain.panel_model import PanelLinks, panel_links
from tests.unit.domain.panel_helpers import BIDI, XSS

NOW = datetime(2026, 11, 14, 20, 24, 31, tzinfo=UTC)
KEYS = (
    ("preflight", "Conferência"),
    ("probe", "Alcance"),
    ("scan", "Varredura"),
    ("report", "Achados"),
)


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.found.append((tag, dict(attrs)))


def stages(current: str | None, *, finished: bool = False) -> tuple[LiveStage, ...]:
    built: list[LiveStage] = []
    reached = False
    for key, label in KEYS:
        state: LiveStageState
        if finished:
            state = "done"
        elif key == current:
            state, reached = "running", True
        else:
            state = "pending" if reached else "done"
        built.append(
            LiveStage(
                key=key,  # type: ignore[arg-type]
                label=label,
                state=state,
                seconds=None if state == "pending" else 60.0,
            )
        )
    return tuple(built)


def view(phase: LivePhase = "running", **changes: object) -> LiveView:
    base: dict[str, object] = {
        "product": "clinica-piloto",
        "product_name": "Clinica Piloto",
        "run_id": "2026-11-14T20-16-00Z-clinica-piloto-ab12",
        "phase": phase,
        "started_at": datetime(2026, 11, 14, 20, 16, tzinfo=UTC),
        "updated_at": NOW,
        "elapsed_seconds": 480.0,
        "limit_minutes": 30,
        "fence_mode": "strict",
        "stages": stages("scan"),
        "functions_tried": 30,
        "functions_reached": 27,
        "scan_done": 10,
        "scan_total": 26,
        "current_function": "Cadastrar paciente",
        "allowed": 3420,
        "denied": 3610,
        "outside_allow": 0,
        "links": panel_links("clinica-piloto"),
    }
    base.update(changes)
    return LiveView(**base)  # type: ignore[arg-type]


def test_while_running_the_page_reloads_every_fifteen_seconds_and_shows_the_update_time() -> None:
    page = render_live(view())

    assert f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">' in page
    assert REFRESH_SECONDS == 15
    assert "atualizado às 20:24:31" in page
    assert "Ao vivo · 8 min" in page
    assert "Se este horário não muda há mais de 1 minuto, o teste parou." in page


def test_the_csp_is_the_same_as_the_other_pages_and_the_page_has_no_script() -> None:
    page = render_live(view())

    assert f'content="{CSP}"' in page
    assert "<script" not in page.lower()
    assert not re.search(r"https?://", page)
    assert "onclick" not in page.lower()
    assert 'lang="pt-BR"' in page


def test_when_it_finishes_there_is_no_reload_and_the_page_links_the_summary_and_the_stages() -> (
    None
):
    page = render_live(view("finished", outcome="finished", stages=stages(None, finished=True)))

    assert "refresh" not in page
    assert "O teste terminou." in page
    assert 'href="summary.html">Resumo</a>' in page
    assert 'href="stages.html">Etapas</a>' in page
    assert "atualizado às" not in page


def test_the_finished_menu_shows_stages_and_not_live_and_every_tab_is_a_link() -> None:
    page = render_live(view("finished", outcome="partial", stages=stages(None, finished=True)))

    assert ">Etapas</a>" in page
    assert "Ao vivo</a>" not in page
    assert 'class="off"' not in page
    assert 'aria-current="page"' not in page
    assert "O teste parou no meio." in page


def test_the_finished_page_tells_why_it_stopped_and_escapes_the_reason() -> None:
    page = render_live(view("finished", outcome="error", reason=f"{XSS}{BIDI}"))

    assert "O teste terminou com erro." in page
    assert "<script" not in page
    assert "&lt;script&gt;" in page
    assert "‮" not in page


def test_while_running_the_menu_has_live_as_the_current_tab_and_the_rest_as_dimmed_text() -> None:
    page = render_live(view())

    assert 'class="on" aria-current="page" href="live.html">Ao vivo' in page
    assert page.count('class="off"') == 5
    parser = Elements()
    parser.feed(page)
    hrefs = {attrs["href"] for tag, attrs in parser.found if tag == "a"}
    assert "stages.html" not in hrefs
    assert "findings.html" not in hrefs


def test_during_the_scan_the_page_names_the_function_and_counts_the_ones_done() -> None:
    page = render_live(view())

    assert '"Cadastrar paciente"' in page
    assert "Função 11 de 26 planejadas" in page
    assert 'aria-label="10 de 26 funções atacadas"' in page
    assert "Varredura · agora" in page
    assert "10 de 26" in page
    assert "Atacando agora" in page
    assert "27 de 30" in page


def test_the_squares_split_done_now_and_queue() -> None:
    page = render_live(view())

    assert page.count('<i class="d"></i>') == 10
    assert page.count('<i class="n"></i>') == 1
    assert 'aria-label="10 atacadas, 1 sendo atacada, 15 na fila"' in page
    assert "atacada (10)" in page
    assert "na fila (15)" in page


def test_without_the_proxy_audit_requests_are_not_measured_never_zero() -> None:
    page = render_live(view(allowed=None, denied=None, outside_allow=None))

    assert "pedidos passaram pela cerca: não medido" in page
    assert "barrados pela cerca: não medido" in page
    assert ">3.420<" not in page


def test_with_the_audit_requests_use_the_thousands_dot() -> None:
    page = render_live(view())

    assert "<b>3.420</b>" in page
    assert "<b>3.610</b>" in page


def test_before_the_scan_there_are_no_squares_and_the_chip_says_preparing() -> None:
    page = render_live(
        view(
            stages=stages("probe"),
            scan_done=None,
            scan_total=None,
            current_function=None,
            allowed=None,
            denied=None,
        )
    )

    assert "Preparando" in page
    assert "Fazendo o sistema responder" in page
    assert 'class="grid"' not in page
    assert 'class="prog"' not in page


def test_the_first_stage_has_no_request_numbers() -> None:
    page = render_live(
        view(
            stages=stages("preflight"),
            scan_done=None,
            scan_total=None,
            functions_tried=None,
            functions_reached=None,
        )
    )

    assert "Conferindo a carta" in page
    assert "pedidos passaram" not in page


def test_stopping_says_so_and_still_reloads() -> None:
    page = render_live(view("stopping"))

    assert "O teste está parando." in page
    assert "Parando" in page
    assert "hdast stop" in page
    assert "refresh" in page


def test_the_page_tells_how_to_stop_the_test() -> None:
    assert 'rode "hdast stop"' in render_live(view()).replace("&quot;", '"')


def test_the_path_links_to_the_indexes_or_is_text_when_they_do_not_exist() -> None:
    linked = render_live(view())
    plain = render_live(view(links=PanelLinks()))

    assert 'href="../../index.html">hdast</a>' in linked
    assert 'href="../../history-clinica-piloto.html">Clinica Piloto</a>' in linked
    assert '<span class="crumb">hdast</span>' in plain
    assert "../../" not in plain


def test_hostile_function_name_is_escaped_and_cut() -> None:
    page = render_live(view(current_function=f"{XSS}{BIDI}" + "x" * 500))

    assert "<script" not in page
    assert "<img" not in page
    assert "&lt;script&gt;" in page
    assert "‮" not in page


def test_a_huge_function_count_falls_back_to_the_progress_bar_without_squares() -> None:
    page = render_live(view(scan_total=5000, scan_done=100))

    assert 'class="grid"' not in page
    assert 'class="prog"' in page


def test_the_track_marks_the_running_stage_and_the_next_ones_as_to_come() -> None:
    page = render_live(view())

    assert page.count('class="seg seg-run"') == 1
    assert page.count('class="seg seg-no"') == 1
    assert "a seguir" in page
    assert "feita" in page


def test_the_page_never_says_safe_or_approved() -> None:
    for phase in ("running", "stopping", "finished"):
        page = re.sub(r"<style>.*?</style>", "", render_live(view(phase)), flags=re.S)
        assert not re.search(r"\b(seguro|segura|aprovad[oa])\b", page, flags=re.I)
