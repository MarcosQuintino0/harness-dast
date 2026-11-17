"""Página "Ao vivo" (`live.html`): em que etapa o teste está. Módulo puro.

Fiel a `docs/design/execution-panel/screens/live.html` e aos estados de `system/states.html`:
trilho de etapas, "atacando agora", quadrados das funções, pedidos e barrados, e o aviso de como
parar. Sem JavaScript: a CLI regrava a página e ela se recarrega sozinha a cada 15 segundos
(`<meta http-equiv="refresh">`), então o horário da última gravação fica sempre ao lado de "Ao
vivo". Quando o teste termina, a página é regravada uma última vez SEM a recarga e liga para o
Resumo e para as Etapas; o menu volta a ser o das páginas do painel ("Etapas" no lugar de "Ao
vivo"). Durante o teste, as abas cujas páginas ainda não existem saem como texto apagado.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel.format import (
    NO_DATA,
    capitalize_first,
    fmt_clock,
    fmt_count,
    fmt_datetime,
    fmt_duration,
    pick,
    plain_stop_reason,
    plural,
    x_of_y,
)
from harness_dast.domain.panel.layout import (
    STATE_CHIP,
    MarkerKind,
    TabItem,
    card,
    chip,
    crumbs,
    document,
    heading,
    row,
    stat,
    status_box,
    tabs_nav,
)
from harness_dast.domain.panel.live_model import LiveStage, LiveView
from harness_dast.domain.panel.pages import PAGES

LIVE_FILE: Final = "live.html"
REFRESH_SECONDS: Final = 15
"""Intervalo da recarga automática da página ao vivo."""

_MAX_SQUARES: Final = 200
_FLOOR: Final = 0.12
_OUTCOME_TITLE: Final = {
    "finished": "O teste terminou.",
    "partial": "O teste parou no meio.",
    "error": "O teste terminou com erro.",
}
_DOING: Final = {
    "preflight": "Conferindo a carta, o Swagger e o login das contas de teste",
    "probe": "Fazendo o sistema responder: tentando cada função de verdade",
    "scan": "Atacando as funções com o ZAP, uma por vez",
    "authz": "Comparando o que cada conta enxerga e altera",
    "negative": "Mandando valores que o contrato proíbe, um por vez",
    "report": "Organizando os achados",
}
_SEG_CLASS: Final = {
    "done": "",
    "running": " seg-run",
    "pending": " seg-no",
    "skipped": " seg-no",
    "cut": " seg-cut",
}
_WITH_REQUESTS: Final = ("scan", "authz", "negative", "report")
"""Etapas em que "pedidos e barrados" fazem sentido (antes da varredura não há pedido de ataque)."""
_ROW_KIND: Final[dict[str, MarkerKind]] = {"done": "ok", "running": "run", "cut": "am"}
_STOP_TEXT: Final = (
    'Para parar o teste, diga ao agente "pare o teste" ou rode "hdast stop" em outro terminal. '
    "O que já foi feito vira resultado parcial."
)
_STALE: Final = "Se este horário não muda há mais de 1 minuto, o teste parou. Pergunte ao agente."


def _after_cut(stage: LiveStage, view: LiveView) -> bool:
    """Etapa feita DEPOIS de uma etapa cortada: o que ela fez vale só com o que veio até aí."""
    if stage.state != "done":
        return False
    keys = [item.key for item in view.stages]
    return any(
        item.state == "cut" and keys.index(item.key) < keys.index(stage.key) for item in view.stages
    )


def _stage_detail(stage: LiveStage, view: LiveView) -> str:
    if stage.state == "running":
        text = fmt_duration(stage.seconds) if stage.seconds is not None else "agora"
        if stage.key == "scan" and view.scan_total:
            text += f" · {x_of_y(view.scan_done or 0, view.scan_total)}"
        return text
    if stage.state == "done" and _after_cut(stage, view):
        return "só com o que veio até aí"
    if stage.state == "done":
        return f"{fmt_duration(stage.seconds)} · feita" if stage.seconds is not None else "feita"
    if stage.state == "cut":
        where = (
            f" · {x_of_y(view.scan_done or 0, view.scan_total)}"
            if stage.key == "scan" and view.scan_total
            else ""
        )
        return f"parou aqui{where}"
    return "não rodou" if stage.state == "skipped" else "a seguir"


def _track(view: LiveView) -> str:
    known = [item.seconds for item in view.stages if item.seconds]
    total = sum(known)
    segments: list[str] = []
    for stage in view.stages:
        width = max(stage.seconds or 0.0, total * _FLOOR) if total else 1.0
        label = stage.label + (" · agora" if stage.state == "running" else "")
        css = " seg-cut" if _after_cut(stage, view) else _SEG_CLASS[stage.state]
        segments.append(
            f'<div class="seg{css}" style="flex: {width:.2f} 1 0">'
            f"<b>{h.plain(label)}</b><span>{h.plain(_stage_detail(stage, view))}</span></div>"
        )
    return card(f'<div class="track">{"".join(segments)}</div>')


def _current(view: LiveView) -> LiveStage | None:
    return next((item for item in view.stages if item.state == "running"), None)


def _squares(view: LiveView) -> str:
    total, done = view.scan_total, view.scan_done
    if not total or done is None or total > _MAX_SQUARES:
        return ""
    now = 1 if view.phase == "running" and done < total else 0
    queue = total - done - now
    cells = '<i class="d"></i>' * done + '<i class="n"></i>' * now + "<i></i>" * queue
    aria = f"{done} atacadas, {now} sendo atacada, {queue} na fila"
    legend = (
        f'<span><i class="dotk k-ok" style="border-radius: 2px"></i>atacada ({done})</span>'
        f'<span><i class="dotk k-run" style="border-radius: 2px"></i>agora ({now})</span>'
        f'<span><i class="dotk k-no" style="border-radius: 2px"></i>na fila ({queue})</span>'
    )
    return card(
        heading(pick(total, "A única função planejada", f"As {total} funções planejadas"))
        + f'<div class="grid" role="img" aria-label="{h.plain(aria)}">{cells}</div>'
        f'<div class="lg">{legend}</div>',
        style="flex: 1 1 280px",
    )


def _requests_stats(view: LiveView) -> str:
    def number(value: int | None, caption: str, one: str | None = None) -> str:
        if value is None:
            return (
                f'<div class="stat"><b class="mu">{NO_DATA}</b>'
                f"<span>{h.plain(caption)}: não medido</span></div>"
            )
        return stat(fmt_count(value), pick(value, one or caption, caption))

    reached = ""
    if view.functions_tried is not None and view.functions_reached is not None:
        reached = stat(
            x_of_y(view.functions_reached, view.functions_tried),
            pick(
                view.functions_tried,
                "função tentada respondeu no alcance",
                "funções tentadas responderam no alcance",
            ),
        )
    return (
        '<div class="stats" style="margin-top: 6px">'
        f"{reached}"
        f"{number(view.allowed, 'pedidos passaram pela cerca', 'pedido passou pela cerca')}"
        f"{number(view.denied, 'barrados pela cerca', 'barrado pela cerca')}"
        f"{number(view.outside_allow, 'fora da carta')}</div>"
    )


def _hero(view: LiveView) -> str:
    now = _current(view)
    if view.phase == "stopping":
        return card(
            f"<div>{chip('Parando', 'am')}</div>"
            '<h1 class="big">O teste está parando.</h1>'
            '<p class="mu">A trava de emergência foi acionada (hdast stop). O que já foi feito '
            "vira resultado parcial. Esta página mostra o fim assim que o teste encerrar.</p>",
            style="padding: 24px 26px",
        )
    if now is not None and now.key == "scan" and view.scan_total:
        done = view.scan_done or 0
        shown = min(done + 1, view.scan_total)
        name = h.text(view.current_function or "função em ataque", 200)
        percent = round(done / view.scan_total * 100)
        aria = (
            f"{done} de {view.scan_total} "
            f"{pick(view.scan_total, 'função atacada', 'funções atacadas')}"
        )
        return card(
            f"<div>{chip('Atacando agora', 'run')}</div>"
            f'<h1 class="big">"{name}"</h1>'
            f'<p class="mu">Função {fmt_count(shown)} de '
            f"{fmt_count(view.scan_total)} planejadas</p>"
            f'<div class="prog" role="img" aria-label="{h.plain(aria)}">'
            f'<i style="width: {percent}%"></i></div>' + _requests_stats(view),
            style="padding: 24px 26px",
        )
    text = _DOING.get(now.key, "Preparando o teste") if now else "Preparando o teste"
    extra = _requests_stats(view) if now is not None and now.key in _WITH_REQUESTS else ""
    return card(
        f"<div>{chip('Preparando', 'run')}</div>"
        f'<h1 class="big" style="font-size: 24px; max-width: none">{h.plain(text)}</h1>'
        '<p class="sm mu">Os quadrados das funções e os tipos de teste só aparecem na '
        "varredura.</p>" + extra,
        style="padding: 24px 26px",
    )


def _done_card(view: LiveView) -> str:
    rows: list[str] = []
    for index, item in enumerate(view.stages):
        kind = "am" if _after_cut(item, view) else _ROW_KIND.get(item.state, "no")
        time = (
            f'<span class="end">{h.plain(fmt_duration(item.seconds))}</span>'
            if item.state == "done" and item.seconds is not None
            else ""
        )
        body = (
            h.plain(item.label)
            if item.state in ("done", "running", "cut")
            else f'<span class="mu">{h.plain(item.label)}</span>'
        )
        rows.append(row(kind, body, end=time, first=index == 0))
    return card(
        heading("O que já terminou") + f"<div>{''.join(rows)}</div>"
        f'<p class="sm mu">{h.plain(_STOP_TEXT)}</p>'
    )


def _finished_card(view: LiveView) -> str:
    outcome = view.outcome or "partial"
    why = capitalize_first(plain_stop_reason(view.reason or "", view.limit_minutes))
    reason = f'<p class="mu">{h.text(why.rstrip(". "), 400)}.</p>' if view.reason else ""
    links = (
        '<div class="r"><span>Veja o resultado em '
        '<a href="summary.html">Resumo</a> e o que cada etapa fez em '
        '<a href="stages.html">Etapas</a>.</span></div>'
    )
    return card(
        f"<div>{chip(STATE_CHIP[outcome][1], STATE_CHIP[outcome][0])}</div>"
        f'<h1 class="big">{h.plain(_OUTCOME_TITLE[outcome])}</h1>{reason}{links}',
        style="padding: 24px 26px",
    )


def _tabs(view: LiveView) -> str:
    if view.phase == "finished":
        items = [TabItem(page.file, page.label) for page in PAGES]
        return tabs_nav(items, None)
    items = []
    for page in PAGES:
        if page.file == "stages.html":
            items.append(TabItem(LIVE_FILE, "Ao vivo"))
        else:
            items.append(TabItem(page.file, page.label, enabled=False))
    return tabs_nav(items, LIVE_FILE)


def _status(view: LiveView) -> str:
    mode = {"strict": "modo estrito", "wide": "modo amplo"}.get(view.fence_mode or "")
    fence = f'<span class="sm mu">Cerca: {h.plain(mode)}</span>' if mode else ""
    if view.phase == "finished":
        outcome = view.outcome or "partial"
        return status_box(fence + chip(STATE_CHIP[outcome][1], STATE_CHIP[outcome][0]))
    when = f"atualizado às {fmt_clock(view.updated_at)}"
    elapsed = f" · {fmt_duration(view.elapsed_seconds)}" if view.elapsed_seconds is not None else ""
    word = "Parando" if view.phase == "stopping" else "Ao vivo"
    return status_box(
        f'{fence}<span class="mu sm">{h.plain(when)}</span>'
        + chip(word + elapsed, "am" if view.phase == "stopping" else "run")
    )


def render_live(view: LiveView) -> str:
    """Página `live.html` completa (com a recarga automática só enquanto o teste roda)."""
    header = (
        crumbs(
            view.product_name,
            fmt_datetime(view.started_at),
            view.links,
            when_href="summary.html" if view.phase == "finished" else LIVE_FILE,
        )
        + f"\n{_tabs(view)}\n{_status(view)}"
    )
    running = view.phase != "finished"
    if running:
        limit = (
            f" Prazo do perfil: {plural(view.limit_minutes, 'minuto', 'minutos')}."
            if view.limit_minutes
            else ""
        )
        note = card(
            f'<p class="sm mu">{h.plain(_STALE)}{h.plain(limit)}</p>'
            '<p class="sm mu">As outras abas aparecem quando o teste terminar.</p>',
            style="padding: 14px 22px",
        )
        left = (
            '<div style="flex: 1.25 1 520px; display: flex; flex-direction: column; gap: 16px; '
            f'min-width: 0">{_hero(view)}{_squares(view)}</div>'
        )
        right = (
            '<div style="flex: 1 1 400px; display: flex; flex-direction: column; gap: 16px; '
            f'min-width: 0">{_done_card(view)}{note}</div>'
        )
        main = f'{_track(view)}\n<div class="g">{left}{right}</div>'
    else:
        main = f"{_track(view)}\n{_finished_card(view)}"
    return document(
        title=f"Ao vivo · {view.product_name}",
        header=header,
        main=main,
        refresh_seconds=REFRESH_SECONDS if running else None,
    )
