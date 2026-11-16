"""Aba Cobertura do painel (`coverage.html`): o que foi e o que não foi testado. Módulo puro.

Fiel a `docs/design/execution-panel/screens/coverage.html` e aos estados "modo amplo", "tudo
testado" e "tráfego não medido" de `system/states.html`: um quadro de números, o mapa das
funções por parte do sistema, a cerca (`panel_fence`) e "o que ficou de fora", cada item com o
risco de não ter testado e quem destrava. Estado nunca só por cor: forma, palavra da lista
fechada (`FUNCTION_STATE_WORDS`) e, para quem não foi testada, o motivo. Texto do OpenAPI sai
por `h.text`; texto nosso, por `h.plain`. Nunca diz "seguro".
"""

from collections import Counter
from collections.abc import Sequence
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_fence import render_fence
from harness_dast.domain.panel_format import (
    FUNCTION_STATE_WORDS,
    NO_DATA,
    fmt_count,
    pick,
    plural,
    x_of_y,
)
from harness_dast.domain.panel_layout import MarkerKind, bar, card, heading, not_measured, row, stat
from harness_dast.domain.panel_model import PanelFunction, PanelView

_MARK: Final = {
    "tested": "k-ok",
    "severe": "k-gr",
    "failed": "k-am",
    "not_tried": "k-am",
    "forbidden": "k-out",
}
_LEGEND: Final = (
    ("tested", "atacada, sem falha grave"),
    ("severe", "atacada, com falha grave"),
    ("not_tried", "não testada"),
    ("forbidden", "proibida pela carta"),
)
_ATTACKED: Final = frozenset({"tested", "severe"})
_MAX_NAMES: Final = 3
_MAX_GROUPS: Final = 6
_MODE_WIDE: Final = "wide"
_NO_MAP: Final = (
    "o painel não achou nem o Swagger nem o probe.json, então não sabe quais funções existem"
)
_UNLOCK: Final[dict[str, str]] = {
    "forbidden": (
        "Destrava: só o dono do produto, pela carta. Função que apaga dados e o login a "
        "ferramenta nunca ataca."
    ),
    "failed": "Destrava: pedir ao agente para melhorar o alcance dessas funções e repetir o teste.",
    "not_tried": "Destrava: repetir o teste até a varredura chegar a elas.",
}
_NOTHING_LEFT: Final = "Nada ficou de fora dentro do que a carta permite."


def _word(state: str) -> str:
    return FUNCTION_STATE_WORDS[state]


def _function_line(item: PanelFunction) -> str:
    mark = (
        f'<i class="dotk {_MARK[item.state]}"></i>'
        f'<span class="vh">{h.plain(_word(item.state))}: </span>'
    )
    name = h.text(item.name, 120)
    if item.state == "severe" and item.finding_ids:
        first, *others = item.finding_ids
        more = "".join(
            f' <a class="sm" href="findings.html#{h.ident(found)}">prova {number}</a>'
            for number, found in enumerate(others, start=2)
        )
        body = f'<b><a href="findings.html#{h.ident(first)}">{name}</a></b>{more}'
        return f'<span class="fn">{mark}{body}</span>'
    if item.state == "forbidden":
        css, body = "fn mu", name
    else:
        css, body = "fn", name
    # A proibida não repete o motivo aqui: ele já está em "O que ficou de fora", agrupado.
    if item.state in ("failed", "not_tried") and item.reason:
        body += f'<span class="sm mu" style="display: block">{h.tagged(item.reason)}</span>'
    return f'<span class="{css}">{mark}{body}</span>'


def _areas(view: PanelView) -> str:
    grouped: dict[str, list[PanelFunction]] = {}
    for item in view.functions:
        grouped.setdefault(item.area, []).append(item)
    blocks = []
    for area, items in grouped.items():
        done = sum(1 for item in items if item.state in _ATTACKED)
        blocks.append(
            f'<div class="area"><h3>{h.text(area, 80)} <span>{h.plain(x_of_y(done, len(items)))}'
            f"</span></h3>{''.join(_function_line(item) for item in items)}</div>"
        )
    return f'<div class="g" style="gap: 20px 28px">{"".join(blocks)}</div>'


def _legend() -> str:
    cells = "".join(
        f'<span><i class="dotk {_MARK[state]}"></i>{h.plain(text)}</span>'
        for state, text in _LEGEND
    )
    return f'<div class="lg">{cells}</div>'


def _summary(view: PanelView) -> str:
    states = Counter(item.state for item in view.functions)
    waiting = states["failed"] + states["not_tried"]
    parts = (
        (float(states["tested"]), "ok"),
        (float(states["severe"]), "gr"),
        (float(waiting), "am"),
        (float(states["forbidden"]), "ln"),
    )
    total = len(view.functions)
    aria = (
        f"{states['tested']} sem falha grave, {states['severe']} com falha grave, "
        f"{plural(waiting, 'não testada', 'não testadas')}, "
        f"{plural(states['forbidden'], 'proibida', 'proibidas')}"
    )
    stats = (
        stat(
            fmt_count(total),
            pick(total, "função do sistema (no Swagger)", "funções do sistema (no Swagger)"),
        )
        + stat(
            fmt_count(states["tested"]),
            pick(states["tested"], "atacada, sem falha grave", "atacadas, sem falha grave"),
            tone="ok",
        )
        + stat(
            fmt_count(states["severe"]),
            pick(states["severe"], "atacada, com falha grave", "atacadas, com falha grave"),
            tone="gr",
        )
        + stat(fmt_count(waiting), pick(waiting, "não testada", "não testadas"), tone="am")
        + stat(
            fmt_count(states["forbidden"]),
            pick(states["forbidden"], "proibida pela carta", "proibidas pela carta"),
            tone="mu",
        )
    )
    return card(
        '<div class="g" style="gap: 16px 48px; align-items: center">'
        f'<div class="stats" style="flex: 1 1 420px">{stats}</div>'
        f'<div style="flex: 1 1 380px">{bar(parts, aria)}</div></div>'
    )


def _names(items: Sequence[PanelFunction]) -> str:
    unique = list(dict.fromkeys(h.text(item.name, 100) for item in items))
    text = ", ".join(unique[:_MAX_NAMES])
    rest = len(unique) - _MAX_NAMES
    return text + (f" e mais {h.plain(fmt_count(rest))}" if rest > 0 else "")


def _function_items(view: PanelView) -> list[tuple[MarkerKind, str]]:
    """Funções que não foram atacadas, agrupadas por estado e motivo."""
    groups: dict[tuple[str, str], list[PanelFunction]] = {}
    for item in view.functions:
        if item.state in _ATTACKED:
            continue
        groups.setdefault((item.state, item.reason or ""), []).append(item)
    rows: list[tuple[MarkerKind, str]] = []
    for (state, reason), items in list(groups.items())[:_MAX_GROUPS]:
        count = h.plain(plural(len(items), "função", "funções"))
        why = f"{h.tagged(reason)} " if reason else ""
        rows.append(
            (
                "am",
                f"<b>{count}: {_names(items)}.</b> "
                f'<span class="mu">{why}Risco: nada foi procurado nelas. '
                f"{h.plain(_UNLOCK[state])}</span>",
            )
        )
    return rows


def _left_out_rows(view: PanelView) -> list[tuple[MarkerKind, str]]:
    rows = _function_items(view)
    wide = view.identity.fence_mode == _MODE_WIDE
    for item in view.left_out:
        text = h.tagged(item.text)
        if item.kind == "authz":
            rows.append(
                (
                    "am",
                    "<b>Uma conta vendo dados de outra.</b> "
                    f'<span class="mu">{text} Risco: falha de autorização pode existir sem ter '
                    "sido vista. Destrava: o dono do produto autoriza o teste entre contas na "
                    "carta.</span>",
                )
            )
        elif item.kind == "negative":
            rows.append(
                (
                    "am",
                    "<b>Valores que o contrato proíbe.</b> "
                    f'<span class="mu">{text} Risco: um campo sem validação pode existir sem ter '
                    "sido visto. Destrava: repetir o teste com o estágio ligado (só leitura, a "
                    "escrita depende da carta).</span>",
                )
            )
        elif item.kind == "scan":
            rows.append(
                (
                    "am",
                    f'<b>Varredura cortada.</b> <span class="mu">{text} Destrava: repetir o '
                    "teste.</span>",
                )
            )
        elif item.kind == "seeded":
            rows.append(
                (
                    "am",
                    "<b>Atacadas a partir de um resultado que não era sucesso.</b> "
                    f'<span class="mu">{h.plain(item.text)}</span>',
                )
            )
        elif item.kind == "fence" and not wide:
            rows.append(
                (
                    "am",
                    "<b>Ataques por endereço disfarçado.</b> "
                    '<span class="mu">Risco: falha de injeção que só aparece nessas formas de '
                    "endereço não foi procurada. Destrava: a carta autorizar o modo amplo (só "
                    "o dono do produto).</span>",
                )
            )
    return rows


def _left_out(view: PanelView) -> str:
    found = _left_out_rows(view) or [("ok", f"<b>{h.plain(_NOTHING_LEFT)}</b>")]
    blind: list[tuple[MarkerKind, str]] = [
        ("no", h.tagged(item.text)) for item in view.left_out if item.kind == "blind"
    ]
    rows = "".join(
        row(kind, body, first=index == 0) for index, (kind, body) in enumerate([*found, *blind])
    )
    return card(heading("O que ficou de fora") + f"<div>{rows}</div>")


def _coverage_details(view: PanelView) -> str:
    banner = (
        "<p><b>Cobertura parcial.</b> Há lacunas ou etapas incompletas.</p>"
        if view.coverage_partial
        else ""
    )
    if not view.coverage_not_tested:
        return banner
    rows = "".join(
        f"<li>{h.text(item.operation_id)} — {h.text(item.method + ' ' + item.path)}: "
        f"probe {h.text(item.probe_outcome or 'não registrado')}; {h.text(item.message)}</li>"
        for item in view.coverage_not_tested
    )
    return banner + card(heading("Operações sem varredura") + f"<ul>{rows}</ul>")


def render_coverage(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Cobertura."""
    if not view.functions:
        return (
            card(
                heading("Mapa do sistema")
                + f'<p class="sm">{not_measured(_NO_MAP)}</p>'
                + f'<div class="r"><span>Funções</span><span class="end">{NO_DATA}</span></div>'
            )
            + f'\n<div class="g">{render_fence(view)}{_left_out(view)}</div>'
        )
    mapa = card(
        heading("Mapa do sistema") + _legend() + _areas(view),
        style="flex: 1.7 1 620px; gap: 18px",
    )
    side = (
        '<div style="flex: 1 1 380px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{render_fence(view)}{_left_out(view)}</div>'
    )
    return f'{_coverage_details(view)}{_summary(view)}\n<div class="g">{mapa}{side}</div>'
