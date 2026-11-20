"""Aba Terminal: fiel a `screens/terminal.html` e ao estado "comando com erro" de `states.html`."""

import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from harness_dast.domain.panel.model import PanelCommand
from harness_dast.domain.panel.pages import render_panel
from tests.unit.domain.panel.helpers import XSS, view

DESIGN = (
    Path(__file__).parents[4] / "docs" / "desenvolver" / "design" / "execution-panel" / "screens"
)
EXTRA_CLASSES = {"crumb", "foot", "vh", "tp", "seg-no", "seg-cut", "nb-cut", "nb-no", "sm"}
DESIGN_ONLY = {"ex", "escuro", "term", "o", "t", "rn", "cur"}
T0 = datetime(2026, 11, 13, 23, 8, 31, tzinfo=UTC)


class Seen(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.classes: set[str] = set()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs += attrs
        for name, value in attrs:
            if name == "class" and value:
                self.classes.update(value.split())


def seen(page: str) -> Seen:
    parser = Seen()
    parser.feed(page)
    return parser


def command(
    minute: int,
    text: str,
    *,
    stage: str | None = None,
    status: str = "ok",
    seconds: float = 21.0,
    output: str = "",
) -> PanelCommand:
    return PanelCommand(
        at=T0 + timedelta(minutes=minute),
        stage=stage,  # type: ignore[arg-type]  # o teste passa só chaves de etapa válidas
        command=text,
        translation=f"Tradução de {text}.",
        status=status,  # type: ignore[arg-type]  # idem: só estados da lista fechada
        seconds=seconds,
        output=output,
    )


def sample() -> tuple[PanelCommand, ...]:
    return (
        command(0, "hdast doctor vampi", output="código de saída: 0"),
        command(1, "hdast spec inspect vampi"),
        command(2, "hdast probe vampi", stage="probe", status="partial", output="status: x"),
        command(
            3,
            "hdast preflight vampi",
            stage="preflight",
            status="error",
            output="código de saída: 3\nerro: PREFLIGHT_FAILED\nAs contas não entraram.",
        ),
        command(4, "hdast run vampi", stage="scan", seconds=1140),
    )


def page_for(commands: tuple[PanelCommand, ...] | None, **changes: object) -> str:
    return render_panel(view(commands=commands, **changes))["terminal.html"]


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


# ---------------------------------------------------------------- fidelidade ao desenho


def test_the_page_uses_only_the_design_classes_plus_the_known_additions() -> None:
    design = seen((DESIGN / "terminal.html").read_text(encoding="utf-8"))

    assert seen(page_for(sample())).classes <= design.classes | EXTRA_CLASSES


def test_the_page_has_the_main_blocks_of_the_design() -> None:
    design = seen((DESIGN / "terminal.html").read_text(encoding="utf-8"))
    generated = seen(page_for(sample()))

    missing = design.classes - generated.classes - DESIGN_ONLY
    assert not missing
    assert {
        "cmd",
        "grp",
        "hr",
        "tm",
        "scroll",
        "lg",
        "ch-ok",
        "ch-am",
        "ch-gr",
    } <= generated.classes
    assert "ex" not in generated.classes


def test_the_card_has_the_column_header_and_each_command_has_the_five_cells() -> None:
    page = page_for(sample())

    for label in ("Hora", "Comando", "O que quer dizer", "Resultado", "Tempo"):
        assert f'<span class="sm mu">{label}</span>' in page or f">{label}</span>" in page
    row = re.search(r'<div class="cmd">(.*?)</div>', page[page.index("doctor") - 200 :], re.S)
    assert row is not None
    assert row.group(1).count("<span") >= 4
    assert "<code>$ hdast doctor vampi</code>" in page


def test_the_side_cards_are_the_ones_of_the_design() -> None:
    text = main_text(page_for(sample()))

    for title in ("Como ler", "O agente só pode", "Resultados"):
        assert title in text
    assert "terminou como esperado" in text
    assert "terminou, mas falta ajustar" in text
    assert "não terminou" in text
    assert "Quem garante é o programa hdast, não a boa vontade do agente." in text


# ---------------------------------------------------------------- conteúdo


def test_commands_come_in_order_with_clock_translation_state_and_duration() -> None:
    text = main_text(page_for(sample()))

    assert (
        text.index("hdast doctor vampi")
        < text.index("hdast spec inspect")
        < text.index("hdast run")
    )
    assert "20:08:31" in text  # 23:08:31 UTC, no fuso do painel (-03:00)
    assert "Tradução de hdast doctor vampi." in text
    assert "21 s" in text
    assert "19 min" in text


def test_the_heading_counts_the_commands() -> None:
    assert "Os comandos deste teste: 5" in main_text(page_for(sample()))


def test_commands_are_grouped_by_stage_and_preparation_has_no_number() -> None:
    page = page_for(sample())

    assert '<p class="grp">Preparação ' in page
    assert '<p class="grp">2 · Alcance ' in page
    assert '<p class="grp">1 · Conferência ' in page
    assert '<p class="grp">3 · Varredura ' in page


def test_every_state_has_a_word_and_not_only_a_color() -> None:
    page = page_for(sample())

    assert '<span class="chip ch-ok">ok</span>' in page
    assert '<span class="chip ch-am">parcial</span>' in page
    assert '<span class="chip ch-gr">erro</span>' in page


def test_the_error_command_shows_its_message_open_and_the_ok_one_closed() -> None:
    page = page_for(sample())

    assert "<details" in page
    opened = re.findall(r"<details[^>]*open[^>]*>.*?</details>", page, re.S)
    assert any("PREFLIGHT_FAILED" in item and "As contas não entraram." in item for item in opened)
    closed = [m for m in re.findall(r"<details[^>]*>", page) if "open" not in m]
    assert closed  # o doctor, que deu certo, vem fechado
    assert any(
        "código de saída: 0" in part
        for part in re.findall(r"<details style[^>]*>.*?</details>", page, re.S)
    )


def test_the_group_row_sums_the_durations() -> None:
    assert "1 comando · 19 min" in main_text(page_for(sample()))


def test_a_short_command_says_less_than_one_second_and_never_zero() -> None:
    page = page_for((command(0, "hdast version", seconds=0.2),))

    assert "menos de 1 s" in page
    assert ">0 s<" not in page


def test_tokens_per_command_are_not_invented() -> None:
    text = main_text(page_for(sample()))

    assert "Tempo · tokens" not in text
    assert "Os tokens por comando ainda não são medidos" in text


def test_tokens_show_when_the_command_has_them() -> None:
    page = page_for((command(0, "hdast doctor vampi").model_copy(update={"tokens": 4000}),))

    assert "Tempo · tokens" in page
    assert "21 s · 4 mil" in page


# ---------------------------------------------------------------- sem diário e linhas puladas


def test_without_a_diary_the_page_says_the_diary_started_in_version_1_2() -> None:
    page = page_for(None)
    text = main_text(page)

    assert "Sem diário de comandos para este teste." in text
    assert "O diário de comandos começou na versão 1.2; este teste é anterior" in text
    assert 'class="cmd"' not in page
    assert "Como ler" in text


def test_a_diary_that_exists_without_a_command_of_this_test_says_exactly_that() -> None:
    text = main_text(page_for(()))

    assert "O diário de comandos existe, mas não tem nenhum comando deste teste." in text
    assert "começou na versão 1.2" not in text
    assert "anterior" not in text


def test_skipped_lines_are_counted_on_the_page() -> None:
    text = main_text(page_for(sample(), commands_skipped=3))

    assert "3 linhas do diário estavam corrompidas e foram puladas" in text


def test_one_skipped_line_uses_the_singular() -> None:
    assert "1 linha do diário estavam" in main_text(page_for(sample(), commands_skipped=1))


# ---------------------------------------------------------------- segurança


def test_hostile_command_text_never_becomes_markup() -> None:
    page = page_for((command(0, f"hdast {XSS}", output=XSS + "\x1b[31m‮x"),))
    parsed = seen(page)

    assert "<script" not in page
    assert "<img" not in page
    assert "\x1b" not in page
    assert "‮" not in page
    assert not any(name.startswith("on") for name, _ in parsed.attrs)
    assert "&lt;script&gt;" in page


def test_a_token_shaped_value_in_the_diary_is_never_shown() -> None:
    leaked = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
    page = page_for(
        (
            command(
                0, f"hdast probe vampi --note {leaked}", status="partial", output=f"id: {leaked}"
            ),
        )
    )

    assert leaked not in page
    assert "eyJhbGciOiJIUzI1NiJ9" not in page


def test_the_page_has_no_script_external_resource_or_event_handler() -> None:
    for commands in (sample(), None):
        page = page_for(commands)
        assert "<script" not in page.lower()
        assert "onclick" not in page.lower()
        assert not re.search(r"https?://", page)


# ---------------------------------------------------------------- virada de dia


MIDNIGHT = datetime(2026, 11, 14, 2, 50, 31, tzinfo=UTC)  # 23:50 no fuso do painel (UTC-3)


def test_the_date_appears_only_on_the_command_where_the_day_changes() -> None:
    before = command(0, "hdast doctor vampi").model_copy(update={"at": MIDNIGHT})
    after = command(0, "hdast probe vampi", stage="probe").model_copy(
        update={"at": MIDNIGHT + timedelta(minutes=20)}
    )
    text = main_text(page_for((before, after)))

    assert "14/11 00:10:31" in text
    assert "13/11 23:50:31" not in text
    assert " 23:50:31" in text


def test_a_list_inside_one_day_never_shows_a_date() -> None:
    text = main_text(page_for(sample()))

    assert not re.search(r"\d\d/\d\d \d\d:\d\d:\d\d", text)
