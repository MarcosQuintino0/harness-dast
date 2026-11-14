"""Aba Tempo e tokens do painel (`time-and-tokens.html`): quanto tempo e quanto trabalho.

Fiel a `docs/design/execution-panel/screens/time-and-tokens.html` e ao estado "teste sem medição"
de `system/states.html`: números em destaque, a tabela por etapa (tempo em branco, tokens em
cinza, barras com `role="img"`) e, na coluna da direita, regras do ZAP, funções, lacunas e regras
desligadas (`panel_rules`). A CLI não mede tokens: eles vêm de `agent-metrics.json`, quando a
avaliação cega o grava na pasta da execução. Sem ele, traço e a explicação, nunca zero. As
frases de "onde foi o tempo" saem dos números do teste, nunca de um texto fixo. Módulo puro.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_bars import cost_bar, seconds_text, share
from harness_dast.domain.panel_build_measure import OTHER_TOKENS
from harness_dast.domain.panel_format import (
    NO_DATA,
    STAGE_WORDS,
    fmt_count,
    fmt_duration,
    fmt_tokens,
    pick,
)
from harness_dast.domain.panel_layout import card, heading, not_measured, row, stat
from harness_dast.domain.panel_model import PanelStage, PanelView
from harness_dast.domain.panel_rules import (
    render_disabled,
    render_functions,
    render_gaps,
    render_rules,
)

_NOT_MEASURED_CELL: Final = '<span class="mu">— não medido</span>'
_NO_TOKENS: Final = (
    "a CLI não mede os tokens: eles vêm de agent-metrics.json, gravado pela avaliação cega na "
    "pasta da execução (teste antigo, sem medição)"
)
_OTHER_LABEL: Final = "Outras tarefas do agente"


def _scan_stage(view: PanelView) -> PanelStage | None:
    return next((item for item in view.stages if item.key == "scan"), None)


def _stats(view: PanelView) -> str:
    duration = view.identity.duration_seconds
    scan = _scan_stage(view)
    scan_seconds = scan.seconds if scan and scan.state != "pending" else None
    total = stat(
        fmt_duration(duration) if duration is not None else NO_DATA,
        "do começo ao fim" if duration is not None else "do começo ao fim · não medido",
    )
    tokens = view.measurements.tokens_total
    second = stat(
        fmt_tokens(tokens) if tokens is not None else NO_DATA,
        "tokens (trabalho do agente de IA)" if tokens is not None else "tokens · não medido",
    )
    if scan_seconds is None:
        third = stat(NO_DATA, "só de varredura · não medido")
    else:
        part = f" ({share(scan_seconds, duration)} do tempo)" if duration else ""
        third = stat(fmt_duration(scan_seconds), f"só de varredura{part}")
    traffic = view.traffic
    if view.traffic_measured and traffic is not None:
        sent = traffic.allowed + traffic.denied
        fourth = stat(
            fmt_count(sent), pick(sent, "pedido de ataque tentado", "pedidos de ataque tentados")
        )
    else:
        fourth = stat(NO_DATA, "pedidos de ataque tentados · não medido")
    attacked = view.verdict.functions_attacked
    fifth = (
        stat(fmt_count(attacked), pick(attacked, "função atacada", "funções atacadas"))
        if attacked is not None
        else stat(NO_DATA, "funções atacadas · não medido")
    )
    return card(f'<div class="stats">{total}{second}{third}{fourth}{fifth}</div>')


def _time_cell(stage: PanelStage, whole: float) -> str:
    if stage.state in ("pending", "skipped"):
        return f'<span class="mu">{h.plain(STAGE_WORDS[stage.state])}</span>'
    if stage.seconds is None:
        return _NOT_MEASURED_CELL
    fraction = stage.seconds / whole if whole else 0.0
    text = seconds_text(stage.seconds)
    aria = h.plain(f"{stage.label}: {text}, {share(stage.seconds, whole)} do tempo")
    return cost_bar(fraction, text, aria)


def _token_cell(label: str, tokens: int | None, whole: int) -> str:
    if tokens is None:
        return _NOT_MEASURED_CELL
    text = fmt_tokens(tokens)
    aria = h.plain(f"{label}: {text} tokens, {share(tokens, whole)} do total")
    return cost_bar(tokens / whole if whole else 0.0, text, aria, grey=True)


def _stage_rows(view: PanelView, whole_time: float, whole_tokens: int) -> str:
    rows = [
        '<div class="cost" style="border-top: 0"><span class="sm mu">Etapa</span>'
        '<span class="sm mu">Tempo</span><span class="sm mu">Tokens do agente</span></div>'
    ]
    for number, stage in enumerate(view.stages, start=1):
        rows.append(
            f'<div class="cost"><span>{number} · {h.plain(stage.label)}</span>'
            f"{_time_cell(stage, whole_time)}"
            f"{_token_cell(stage.label, stage.tokens, whole_tokens)}</div>"
        )
    by_stage = view.measurements.tokens_by_stage
    if by_stage and by_stage.get(OTHER_TOKENS):
        rows.append(
            f'<div class="cost"><span>{h.plain(_OTHER_LABEL)}</span>'
            f'<span class="mu">{NO_DATA}</span>'
            f"{_token_cell(_OTHER_LABEL, by_stage[OTHER_TOKENS], whole_tokens)}</div>"
        )
    duration = view.identity.duration_seconds
    time_total = fmt_duration(duration) if duration is not None else "— não medido"
    tokens = view.measurements.tokens_total
    token_total = fmt_tokens(tokens) if tokens is not None else "— não medido"
    rows.append(
        '<div class="cost" style="border-top: 1px solid var(--mu)"><b>Total</b>'
        f"<b>{h.plain(time_total)}</b><b>{h.plain(token_total)}</b></div>"
    )
    return "".join(rows)


def _reading(view: PanelView, whole_time: float, whole_tokens: int) -> str:
    """Onde foi o tempo e onde foram os tokens, em frases tiradas dos números do teste."""
    timed = [item for item in view.stages if item.seconds]
    parts: list[str] = []
    if timed and whole_time:
        top = max(timed, key=lambda item: item.seconds or 0.0)
        parts.append(
            f"A maior parte do tempo foi da etapa {top.label} "
            f"({share(top.seconds or 0.0, whole_time)} do tempo)."
        )
    by_stage = view.measurements.tokens_by_stage
    if by_stage and whole_tokens:
        label = next(
            (
                item.label
                for item in view.stages
                if by_stage.get(item.key) == max(by_stage.values())
            ),
            _OTHER_LABEL.lower(),
        )
        parts.append(
            f"A maior parte dos tokens foi da etapa {label} "
            f"({share(max(by_stage.values()), whole_tokens)} dos tokens medidos)."
        )
    if not parts:
        return ""
    return f'<p class="sm mu" style="margin-top: 12px">{h.plain(" ".join(parts))}</p>'


def _per_stage(view: PanelView) -> str:
    summed = sum(item.seconds or 0.0 for item in view.stages if item.state != "pending")
    whole_time = max(view.identity.duration_seconds or 0.0, summed)
    by_stage = view.measurements.tokens_by_stage
    whole_tokens = sum(by_stage.values()) if by_stage else 0
    return card(
        heading("Por etapa", style="margin-bottom: 10px")
        + _stage_rows(view, whole_time, whole_tokens)
        + _reading(view, whole_time, whole_tokens),
        style="gap: 0",
    )


def _tokens_card(view: PanelView) -> str:
    meas = view.measurements
    detail = meas.tokens_breakdown
    if detail is None:
        return card(
            heading("Tokens do agente", style="margin-bottom: 6px")
            + f'<p class="sm">{not_measured(_NO_TOKENS)}</p>',
            style="gap: 0",
        )
    model = f"modelo {meas.agent_model}" if meas.agent_model else ""
    lines = [
        ("Entrada", detail.input, ""),
        ("Saída", detail.output, ""),
        ("Entrada gravada no cache", detail.cache_written, ""),
        ("Entrada relida do cache", detail.cache_read, "não entra na soma"),
    ]
    rows = "".join(
        row(
            "no",
            h.plain(label),
            end=f'<span class="end">{h.plain(fmt_tokens(value))}'
            f"{' · ' + h.plain(note) if note else ''}</span>",
            first=index == 0,
        )
        for index, (label, value, note) in enumerate(lines)
    )
    note = (
        '<p class="sm mu" style="margin-top: 8px">O total de tokens soma entrada, saída e '
        "entrada gravada no cache. O cache relido é o mesmo contexto lido de novo a cada passo: "
        "somá-lo faria o número crescer com a quantidade de passos, não com o trabalho.</p>"
    )
    return card(
        heading("Tokens do agente", note=model, style="margin-bottom: 6px") + rows + note,
        style="gap: 0",
    )


def render_time(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Tempo e tokens."""
    left = (
        '<div style="flex: 1.6 1 560px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{_per_stage(view)}{_tokens_card(view)}</div>'
    )
    right = (
        '<div style="flex: 1 1 400px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{render_rules(view)}{render_functions(view)}{render_gaps(view)}'
        f"{render_disabled(view)}</div>"
    )
    return f'{_stats(view)}\n<div class="g">{left}{right}</div>'
