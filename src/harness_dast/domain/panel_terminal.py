"""Aba Terminal do painel (`terminal.html`): o que o agente fez, comando por comando. Módulo puro.

Fiel a `docs/design/execution-panel/screens/terminal.html` e ao estado "comando com erro" de
`system/states.html`. Cada comando do diário (ADR 0033), em ordem, mostra a hora, o comando cru,
a frase que o traduz, o estado (palavra, nunca só cor), a duração e a resposta resumida; comando
parcial ou com erro já vem com a resposta aberta. Sem diário para o teste (teste anterior à
versão 1.2), a aba diz isso em vez de inventar uma lista.

A resposta abre e fecha com `<details>`, que é HTML puro (sem JavaScript). Todo texto do diário
passa por `html_safe` (que de novo redige segredo e corta); nada do diário vira marcação.
"""

from itertools import groupby
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_format import fmt_clock, fmt_duration, fmt_tokens, plural
from harness_dast.domain.panel_layout import Tone, card, chip, row
from harness_dast.domain.panel_model import CommandStatus, PanelCommand, PanelView, StageKey

_STATUS: Final[dict[CommandStatus, tuple[Tone, str]]] = {
    "ok": ("ok", "ok"),
    "partial": ("am", "parcial"),
    "error": ("gr", "erro"),
}
_PREPARATION: Final = "Preparação"
_SHORT: Final = "menos de 1 s"
_OUTPUT_LIMIT: Final = 1600


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return _SHORT if seconds < 1 else fmt_duration(seconds)


def _time_cell(item: PanelCommand) -> str:
    text = _duration(item.seconds)
    if item.tokens is not None:
        text += f" · {fmt_tokens(item.tokens)}"
    return text


def _hour(item: PanelCommand, *, new_day: bool) -> str:
    """A hora do comando; com a data (`15/11`) quando é o primeiro comando de um dia novo."""
    clock = fmt_clock(item.at)
    return f"{item.at:%d/%m} {clock}" if new_day and item.at is not None else clock


def _command_row(item: PanelCommand, *, new_day: bool) -> str:
    tone, word = _STATUS[item.status]
    opened = item.status != "ok"
    response = ""
    if item.output:
        response = (
            f'<details style="grid-column: 2 / -1"{" open" if opened else ""}>'
            '<summary class="sm mu">resposta do comando</summary>'
            f'<pre class="term" style="margin-top: 6px">{h.block(item.output, _OUTPUT_LIMIT)}</pre>'
            "</details>"
        )
    style = (
        ' style="background: var(--s2); margin: 0 -12px; padding: 10px 12px; border-radius: 8px"'
    )
    return (
        f'<div class="cmd"{style if opened else ""}>'
        f'<span class="hr">{h.plain(_hour(item, new_day=new_day))}</span>'
        f"<code>$ {h.text(item.command, 300)}</code>"
        f"<span>{h.text(item.translation, 300)}</span>"
        f"<span>{chip(word, tone, dot=False)}</span>"
        f'<span class="tm">{h.plain(_time_cell(item))}</span>{response}</div>'
    )


def _group_title(view: PanelView, stage: StageKey | None) -> str:
    if stage is None:
        return _PREPARATION
    for number, item in enumerate(view.stages, start=1):
        if item.key == stage:
            return f"{number} · {item.label}"
    return stage


def _groups(view: PanelView, commands: tuple[PanelCommand, ...]) -> str:
    parts: list[str] = []
    day = commands[0].at.date() if commands and commands[0].at else None
    for stage, members in groupby(commands, key=lambda item: item.stage):
        group = list(members)
        known = [item.seconds for item in group if item.seconds is not None]
        total = f" · {_duration(sum(known))}" if known else ""
        parts.append(
            f'<p class="grp">{h.text(_group_title(view, stage), 80)} '
            f"<span>{h.plain(plural(len(group), 'comando', 'comandos'))}{h.plain(total)}</span></p>"
        )
        for item in group:
            new_day = item.at is not None and day is not None and item.at.date() != day
            parts.append(_command_row(item, new_day=new_day))
            day = item.at.date() if item.at is not None else day
    return "".join(parts)


def _header(commands: tuple[PanelCommand, ...]) -> str:
    timing = "Tempo · tokens" if any(item.tokens is not None for item in commands) else "Tempo"
    return (
        '<div class="cmd" style="border-top: 0; padding-bottom: 4px; margin-top: 10px">'
        '<span class="sm mu">Hora</span><span class="sm mu">Comando</span>'
        '<span class="sm mu">O que quer dizer</span><span class="sm mu">Resultado</span>'
        f'<span class="sm mu" style="text-align: right">{timing}</span></div>'
    )


def _skipped_note(view: PanelView) -> str:
    if not view.commands_skipped:
        return ""
    lines = plural(view.commands_skipped, "linha do diário", "linhas do diário")
    return (
        f'<p class="sm mu" style="margin-top: 8px">{h.plain(lines)} estavam corrompidas e foram '
        "puladas. Os comandos abaixo são os que deu para ler.</p>"
    )


def _list_card(view: PanelView, commands: tuple[PanelCommand, ...]) -> str:
    return card(
        f'<h2 class="h">Os comandos deste teste: {len(commands)}</h2>'
        f"{_skipped_note(view)}"
        '<div class="scroll"><div style="min-width: 760px">'
        f"{_header(commands)}{_groups(view, commands)}</div></div>",
        style="flex: 3 1 700px; gap: 0",
    )


def _empty_card(view: PanelView) -> str:
    if view.commands is None:
        reason = (
            "<b>Sem diário de comandos para este teste.</b> O diário de comandos começou na "
            "versão 1.2; este teste é anterior, ou foi rodado em outro computador."
        )
    else:
        reason = (
            "<b>O diário de comandos existe, mas não tem nenhum comando deste teste.</b> "
            "Ele só guarda os comandos dados neste computador."
        )
    return card(
        '<h2 class="h" style="font-size: 17px">Os comandos deste teste</h2>'
        + row("no", reason, first=True)
        + '<p class="sm mu">Nada foi inventado no lugar: o que cada etapa fez está na aba '
        "Etapas, e as falhas estão na aba Falhas.</p>",
        style="flex: 3 1 700px",
    )


def _side(commands: tuple[PanelCommand, ...] | None) -> str:
    tokens_note = (
        ""
        if commands and any(item.tokens is not None for item in commands)
        else " Os tokens por comando ainda não são medidos: por isso não aparecem."
    )
    how = card(
        '<h2 class="h">Como ler</h2>'
        '<p class="sm mu">Cada linha é um comando hdast de verdade, na ordem em que foi dado, '
        "pelo agente ou por uma pessoa (o diário não distingue). A frase ao lado é a tradução. "
        "Clique em “resposta do comando” para abrir ou fechar o resumo da resposta; os comandos "
        f"parciais ou com erro já vêm abertos.{tokens_note}</p>"
    )
    rules = card(
        '<h2 class="h">O agente só pode</h2><div>'
        + row(
            "ok",
            "Agir no sistema testado por comandos <b>hdast</b>, nunca por outro meio.",
            first=True,
        )
        + row("ok", "Reduzir limites, nunca aumentar o que a carta permite.")
        + row("ok", "Usar apelidos de conta, nunca ler senhas.")
        + '</div><p class="sm mu">Quem garante é o programa hdast, não a boa vontade do agente.</p>'
    )
    legend = card(
        '<h2 class="h">Resultados</h2>'
        '<div class="lg" style="flex-direction: column; gap: 8px">'
        f"<span>{chip('ok', 'ok', dot=False)} terminou como esperado</span>"
        f"<span>{chip('parcial', 'am', dot=False)} terminou, mas falta ajustar</span>"
        f"<span>{chip('erro', 'gr', dot=False)} não terminou</span></div>"
    )
    return (
        '<div style="flex: 1 1 300px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{how}{rules}{legend}</div>'
    )


def render_terminal(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Terminal."""
    commands = view.commands
    main = _list_card(view, commands) if commands else _empty_card(view)
    return f'<h1 class="vh">Terminal</h1><div class="g">{main}{_side(commands)}</div>'
