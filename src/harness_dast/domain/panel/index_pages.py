"""Páginas dos índices: Produtos (`index.html`) e Histórico de um produto. Módulo puro.

Fiéis a `docs/desenvolver/design/execution-panel/screens/products.html` e `product-history.html`:
mesma
estrutura, classes e textos fixos; só os dados mudam e as marcas "ex." somem. Execução sem
dados aparece como linha "sem dados", nunca some. Link só para arquivo que existe: sem painel
gerado, a data fica como texto com um aviso. Todo texto de arquivo passa por `html_safe`.
"""

from collections.abc import Sequence
from datetime import date
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel.format import (
    NO_DATA,
    RUN_STATE_WORDS,
    fmt_count,
    fmt_date,
    fmt_datetime,
    fmt_duration,
    fmt_tokens,
    plural,
    x_of_y,
)
from harness_dast.domain.panel.index_build import (
    Change,
    comparable,
    diff,
    is_sweep,
    latest_report,
    longest_open,
    previous_of,
)
from harness_dast.domain.panel.index_model import ProductEntry, RunRow
from harness_dast.domain.panel.layout import CSP, MarkerKind, Tone, card, chip, heading, marker
from harness_dast.domain.panel.model import INDEX_FILE, history_file
from harness_dast.domain.panel.style import STYLE

_VERDICT_TONE: Final[dict[str, Tone]] = {"finished": "ok", "partial": "am", "error": "gr"}
_LAST_TESTS: Final = 10
_CHART_RUNS: Final = 8
_CHART_HEIGHT: Final = 70
_EXPIRING_DAYS: Final = 7
_NO_PANEL: Final = "sem painel"
_MIN_POINTS: Final = 2


def render_index_page(*, title: str, crumbs: str, main: str, today: date) -> str:
    """Casca dos índices: sem menu de abas, com a data de geração à direita."""
    return (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        f"<title>{h.plain(title)}</title>\n<style>\n{STYLE}</style>\n</head>\n<body>\n"
        '<div class="tp">\n<header class="top">\n'
        f'<div class="brand"><i></i>{crumbs}</div>\n'
        '<div style="margin-left: auto; display: flex; flex-wrap: wrap; gap: 8px 14px; '
        'align-items: center; padding: 10px 0">'
        f'<span class="mu sm">Página gerada pelo hdast · {h.plain(fmt_date(today))}</span></div>\n'
        f'</header>\n<main class="pg">\n{main}\n</main>\n</div>\n</body>\n</html>\n'
    )


def _when(row: RunRow, *, short: bool) -> str:
    moment = row.started_at
    if moment is None:
        return NO_DATA
    return moment.strftime("%d/%m · %H:%M") if short else fmt_datetime(moment)


def _when_cell(row: RunRow, *, short: bool) -> str:
    text = h.plain(_when(row, short=short))
    if row.panel_link is None:
        return f'{text} <span class="sm mu">{_NO_PANEL}</span>'
    return f'<a href="{h.plain(row.panel_link)}">{text}</a>'


def _verdict_chip(row: RunRow) -> str:
    if row.state == "empty" or row.verdict is None:
        return chip("sem dados", "mu", dot=False)
    tone = _VERDICT_TONE[row.verdict]
    word = RUN_STATE_WORDS[row.verdict]
    return chip(word, tone, dot=False) + (
        ' <span class="sm mu">dados incompletos</span>' if row.state == "partial" else ""
    )


def _functions_cell(row: RunRow) -> str:
    if row.state == "empty" or row.functions_attacked is None:
        return "nenhuma" if row.kind in ("probe", "preflight") else NO_DATA
    if row.functions_basis is None:
        return h.plain(fmt_count(row.functions_attacked))
    return h.plain(x_of_y(row.functions_attacked, max(row.functions_basis, row.functions_attacked)))


def _severe_cell(row: RunRow) -> str:
    if row.severe_count is None:
        return NO_DATA
    if row.severe_count == 0:
        return "0"
    return f'<b style="color: var(--gr)">{row.severe_count}</b>'


def _tokens_cell(row: RunRow) -> str:
    if row.tokens is None:
        return '<span class="mu" title="não medido">—</span>'
    return h.plain(fmt_tokens(row.tokens))


def _duration_cell(row: RunRow) -> str:
    if row.duration_seconds is None:
        return '<span class="mu" title="não medido">—</span>'
    return h.plain(fmt_duration(row.duration_seconds))


def _change_text(change: Change | None, *, first: bool, row: RunRow) -> str:
    if row.state == "empty" or not comparable(row):
        return NO_DATA
    if first:
        return "primeira vez"
    if change is None:
        return NO_DATA
    parts = []
    if change.new:
        parts.append(plural(change.new, "nova", "novas"))
    if change.persistent:
        parts.append(plural(change.persistent, "continua", "continuam"))
    if change.gone:
        parts.append(plural(change.gone, "não apareceu", "não apareceram"))
    return " · ".join(parts) or "sem mudança"


# ---------------------------------------------------------------- produtos


def _card_chip(rows: Sequence[RunRow]) -> str:
    report = latest_report(rows)
    if report is None:
        if rows[0].state == "empty":
            return chip("último teste sem dados", "am")
        return chip("sem relatório de falhas", "mu")
    count = report.severe_count or 0
    if count == 0:
        return chip("Nenhuma falha grave no último relatório", "ok")
    word = "falha grave aberta" if count == 1 else "falhas graves abertas"
    return chip(f"{count} {word}", "gr")


def _letter_line(entry: ProductEntry, today: date) -> str:
    info = entry.info
    last = entry.rows[0]
    mode = info.fence_mode or last.fence_mode
    fence = f" · cerca no {'modo amplo' if mode == 'wide' else 'modo estrito'}" if mode else ""
    if not info.profile_available or info.valid_until is None:
        text = "Carta não consultada: o perfil deste produto não pôde ser lido agora."
        return _line("no", h.plain(text + fence))
    ref = (
        f"Carta {h.ident(info.authorization_reference)}"
        if info.authorization_reference
        else "Carta"
    )
    until = info.valid_until
    left = (until - today).days
    if left < 0:
        return _line("gr", f"{ref} venceu em {h.plain(fmt_date(until))}{h.plain(fence)}")
    if left <= _EXPIRING_DAYS:
        when = "vence hoje" if left == 0 else f"vence em {plural(left, 'dia', 'dias')}"
        return _line("am", f"{ref} {h.plain(when)}{h.plain(fence)}")
    return _line("ok", f"{ref} válida até {h.plain(fmt_date(until))}{h.plain(fence)}")


def _line(kind: MarkerKind, body: str) -> str:
    return (
        f'<div class="r" style="padding-bottom: 0">{marker(kind)}'
        f'<span class="sm">{body}</span></div>'
    )


def _product_card(entry: ProductEntry, today: date) -> str:
    last = entry.rows[0]
    total = next((row.functions_total for row in entry.rows if row.functions_total), None)
    scope = (
        f"{plural(total, 'função', 'funções')} no Swagger · " if total is not None else ""
    ) + "ambiente de teste"
    return (
        f'<a class="card prod" href="{h.plain(history_file(entry.product))}" style="gap: 14px">'
        '<div style="display: flex; justify-content: space-between; gap: 12px; '
        'align-items: flex-start">'
        f'<div><b class="nm">{h.ident(entry.name)}</b><span class="sm mu">{h.plain(scope)}</span>'
        f"</div>{_card_chip(entry.rows)}</div>"
        '<div class="stats">'
        f'<div class="stat"><b>{len(entry.rows)}</b><span>'
        f"{'teste feito' if len(entry.rows) == 1 else 'testes feitos'}</span></div>"
        f'<div class="stat"><b>{h.plain(fmt_date(last.started_at))}</b><span>último teste, '
        f"{h.plain(last.started_at.strftime('%H:%M') if last.started_at else NO_DATA)}</span></div>"
        f'<div class="stat"><b>{_stat_duration(last)}</b><span>duração do último</span></div>'
        f"</div>{_letter_line(entry, today)}</a>"
    )


def _stat_duration(row: RunRow) -> str:
    if row.duration_seconds is None:
        return NO_DATA
    return h.plain(fmt_duration(row.duration_seconds))


def _recent_table(entries: Sequence[ProductEntry]) -> str:
    flat = sorted(
        (row for entry in entries for row in entry.rows), key=lambda r: r.run_id, reverse=True
    )[:_LAST_TESTS]
    names = {entry.product: entry.name for entry in entries}
    head = (
        "<tr><th>Quando</th><th>Produto</th><th>O que rodou</th><th>Funções atacadas</th>"
        "<th>Falhas graves</th><th>Duração</th><th>Tokens</th><th>Como terminou</th></tr>"
    )
    rows = "".join(
        f"<tr><td>{_when_cell(row, short=False)}</td><td>{h.ident(names[row.product])}</td>"
        f"<td>{h.plain(row.what_ran or NO_DATA)}</td><td>{_functions_cell(row)}</td>"
        f"<td>{_severe_cell(row)}</td><td>{_duration_cell(row)}</td><td>{_tokens_cell(row)}</td>"
        f"<td>{_verdict_chip(row)}</td></tr>"
        for row in flat
    )
    return card(
        heading("Últimos testes, de todos os produtos")
        + f'<div class="scroll"><table class="tbl" style="min-width: 860px">{head}{rows}</table>'
        "</div>"
    )


_NEW_PRODUCT: Final = (
    '<div class="card" style="flex: 0.6 1 240px; border-style: dashed; justify-content: center">'
    "<b>Testar um produto novo</b>"
    '<span class="sm mu">Entregue ao agente o Swagger e a carta de autorização do produto. Ele '
    "aparece aqui depois do primeiro teste.</span></div>"
)
_NO_PRODUCT: Final = (
    '<div class="card" style="border-style: dashed"><b>Nenhum produto testado ainda</b>'
    '<span class="sm mu">Entregue ao agente o Swagger e a carta de autorização de um produto. '
    "Ele aparece aqui depois do primeiro teste.</span></div>"
)


def render_products(entries: Sequence[ProductEntry], today: date) -> str:
    """Página `index.html`: um cartão por produto e os últimos testes de todos."""
    tests = sum(len(entry.rows) for entry in entries)
    summary = (
        "nenhum produto testado ainda"
        if not entries
        else f"{plural(len(entries), 'produto testado', 'produtos testados')} · "
        f"{plural(tests, 'teste feito', 'testes feitos')}"
    )
    top = (
        '<div style="display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline; '
        'padding: 8px 0 0"><h1 class="big" style="max-width: none">Produtos</h1>'
        f'<span class="mu">{h.plain(summary)}</span></div>'
    )
    if not entries:
        main = top + f'<div class="g">{_NO_PRODUCT}</div>'
    else:
        cards = "".join(_product_card(entry, today) for entry in entries)
        main = top + f'<div class="g">{cards}{_NEW_PRODUCT}</div>' + _recent_table(entries)
    crumbs = f'<a class="here" href="{INDEX_FILE}">hdast</a>'
    return render_index_page(title="Produtos · hdast", crumbs=crumbs, main=main, today=today)


# ---------------------------------------------------------------- histórico


def _top_card(entry: ProductEntry) -> str:
    info = entry.info
    total = next((row.functions_total for row in entry.rows if row.functions_total), None)
    bits = [
        f"{plural(total, 'função', 'funções')} no Swagger" if total is not None else "",
        "ambiente de teste, dados inventados",
    ]
    if info.profile_available and info.authorization_reference:
        letter = f"carta {h.ident(info.authorization_reference)}"
        if info.valid_until:
            letter += f", válida até {h.plain(fmt_date(info.valid_until))}"
        bits.append(letter)
    sub = " · ".join(item for item in bits if item)
    report = latest_report(entry.rows)
    open_now = (
        f'<b style="color: var(--gr)">{report.severe_count}</b>'
        if report and report.severe_count
        else f"<b>{NO_DATA if report is None else 0}</b>"
    )
    durations = [row.duration_seconds for row in entry.rows if row.duration_seconds is not None]
    tokens = [row.tokens for row in entry.rows if row.tokens is not None]
    total_time = h.plain(fmt_duration(sum(durations))) if durations else NO_DATA
    total_tokens = h.plain(fmt_tokens(sum(tokens))) if tokens else NO_DATA
    return (
        '<section class="card" style="padding: 24px 26px">'
        '<div class="g" style="gap: 20px 48px; align-items: flex-end">'
        '<div style="flex: 1 1 380px; display: flex; flex-direction: column; gap: 8px">'
        f'<h1 class="big" style="max-width: none">{h.ident(entry.name)}</h1>'
        f'<p class="mu">{sub}</p></div>'
        '<div class="stats" style="flex: 1 1 460px">'
        f'<div class="stat"><b>{len(entry.rows)}</b><span>testes feitos</span></div>'
        f'<div class="stat">{open_now}<span>falhas graves abertas</span></div>'
        f'<div class="stat"><b>{total_time}</b><span>de teste, somando tudo</span></div>'
        f'<div class="stat"><b>{total_tokens}</b><span>tokens, somando tudo</span></div>'
        "</div></div></section>"
    )


def _history_table(rows: Sequence[RunRow]) -> str:
    head = (
        "<tr><th>Quando</th><th>O que rodou</th><th>Funções atacadas</th><th>Falhas graves</th>"
        "<th>Mudou desde o anterior</th><th>Duração</th><th>Tokens</th><th>Como terminou</th></tr>"
    )
    lines: list[str] = []
    for index, row in enumerate(rows):
        before = previous_of(rows, index)
        change = diff(before, row) if before is not None else None
        text = _change_text(change, first=before is None, row=row)
        cls = ' class="selrow"' if index == 0 else ""
        lines.append(
            f"<tr{cls}><td>{_when_cell(row, short=True)}</td>"
            f"<td>{h.plain(row.what_ran or NO_DATA)}</td><td>{_functions_cell(row)}</td>"
            f"<td>{_severe_cell(row)}</td><td>{h.plain(text)}</td><td>{_duration_cell(row)}</td>"
            f"<td>{_tokens_cell(row)}</td><td>{_verdict_chip(row)}</td></tr>"
        )
    return (
        heading("Histórico de testes")
        + f'<div class="scroll"><table class="tbl" style="min-width: 780px">{head}'
        f"{''.join(lines)}</table></div>"
        '<p class="sm mu">Clique na data para abrir o painel daquele teste. Cada teste guarda o '
        "seu painel inteiro, com terminal e prova.</p>"
    )


def _trend(rows: Sequence[RunRow]) -> str:
    sweeps = [row for row in reversed(rows) if is_sweep(row)][-_CHART_RUNS:]
    if len(sweeps) < _MIN_POINTS:
        return ""
    counts = [row.severe_count or 0 for row in sweeps]
    top = max(counts) or 1
    bars = "".join(
        f'<div>{value}<i style="height: {round(value / top * _CHART_HEIGHT)}px"></i></div>'
        for value in counts
    )
    labels = "".join(
        f"<span>{h.plain(_when(row, short=True).replace(' · ', ' '))}</span>" for row in sweeps
    )
    aria = "Falhas graves por varredura: " + ", depois ".join(str(value) for value in counts)
    return card(
        heading("Falhas graves a cada varredura completa")
        + f'<div><div class="trend" role="img" aria-label="{h.plain(aria)}">{bars}</div>'
        f'<div class="trendx">{labels}</div></div>'
    )


def _since_card(rows: Sequence[RunRow]) -> str:
    before = previous_of(rows, 0)
    if before is None:
        return ""
    change = diff(before, rows[0])
    if change is None:
        return ""

    def line(kind: MarkerKind, count: int, head: str, items: Sequence[str]) -> str:
        names = h.text(", ".join(items[:3]) + (" e outras" if len(items) > 3 else ""), 300)
        tail = f": {names}" if items else ""
        mute = ' class="mu"' if count == 0 else ""
        return (
            f'<div class="r">{marker("no" if count == 0 else kind)}'
            f"<span{mute}><b>{h.plain(head)}</b>{tail}</span></div>"
        )

    body = (
        line(
            "ok",
            change.gone,
            plural(change.gone, "não apareceu", "não apareceram"),
            change.gone_items,
        )
        + line(
            "gr",
            change.persistent,
            plural(change.persistent, "continua", "continuam"),
            change.persistent_items,
        )
        + line("am", change.new, plural(change.new, "nova", "novas"), change.new_items)
    )
    return card(
        heading("Desde a varredura anterior", note=f"comparado com {_when(before, short=True)}")
        + f"<div>{body}</div>"
        '<p class="sm mu">A comparação é sempre com o último teste do mesmo tipo. Cada falha tem '
        "um código que não muda entre testes. É por ele que o painel sabe se ela é nova ou "
        "continua. Não apareceu não quer dizer corrigida: a função pode não ter sido atacada "
        "desta vez.</p>"
    )


def _oldest_card(rows: Sequence[RunRow]) -> str:
    found = longest_open(rows)
    if not found:
        return ""
    lines = "".join(
        f'<div class="r">{marker("gr")}<span>{h.text(item.title, 200)}</span>'
        f'<span class="end">desde {h.plain(fmt_date(item.since)[:5])} · '
        f"{h.plain(plural(item.tests, 'teste', 'testes'))}</span>"
        "</div>"
        for item in found
    )
    return card(heading("Falhas abertas há mais tempo") + f"<div>{lines}</div>")


def render_history(entry: ProductEntry, today: date) -> str:
    """Página `history-<produto>.html`: os testes do produto e o que mudou entre eles."""
    side = "".join(
        part
        for part in (_trend(entry.rows), _since_card(entry.rows), _oldest_card(entry.rows))
        if part
    )
    sidebar = (
        '<div style="flex: 1 1 340px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{side}</div>'
        if side
        else ""
    )
    table = card(_history_table(entry.rows), style="flex: 2.4 1 700px")
    main = _top_card(entry) + f'<div class="g">{table}{sidebar}</div>'
    crumbs = (
        f'<a href="{INDEX_FILE}">hdast</a><span class="sep">/</span>'
        f'<a class="here" href="{h.plain(history_file(entry.product))}">{h.ident(entry.name)}</a>'
    )
    return render_index_page(title=f"{entry.name} · hdast", crumbs=crumbs, main=main, today=today)
