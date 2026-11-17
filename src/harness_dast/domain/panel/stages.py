"""Aba Etapas do painel (`stages.html`) e o trilho de etapas que o Resumo também usa. Módulo puro.

Fiel a `docs/design/execution-panel/screens/stages.html`: o trilho no tamanho do tempo de cada
etapa, o que aconteceu em cada uma, onde o teste travou e os tipos de teste feitos. Etapa
cortada fica em amarelo e as seguintes em cinza (`system/states.html`). Tempo ou token que não
foi medido aparece como traço com a explicação, nunca como zero.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel.format import (
    STAGE_WORDS,
    fmt_duration,
    fmt_tokens,
    plain_stop_reason,
    plural,
)
from harness_dast.domain.panel.layout import bar, card, heading, not_measured, row, terminal
from harness_dast.domain.panel.model import PanelStage, PanelView

_TITLES: Final[dict[str, str]] = {
    "preflight": "Leu o Swagger e a carta e conferiu o login",
    "probe": "Alcance: fez o sistema responder de verdade",
    "scan": "Varredura: atacou com o ZAP",
    "authz": "Teste entre contas: repetiu pedidos com outra conta",
    "negative": "Valores proibidos: testou o que o contrato não aceita",
    "report": "Organizou os achados",
}
_SEG_CLASS: Final = {"done": "", "cut": " seg-cut", "skipped": " seg-no", "pending": " seg-no"}
_NB_CLASS: Final = {"done": "", "cut": " nb-cut", "skipped": " nb-no", "pending": " nb-no"}
_MAX_SQUARES_FULL: Final = 60
_MAX_SQUARES: Final = 200
_MAX_TRAVAS: Final = 6
_MAX_RULES: Final = 8
_FLOOR: Final = 0.1
_NO_REASON: Final = "O teste não registrou o motivo."


def _no_answer(count: int) -> str:
    return plural(count, "função não respondeu", "funções não responderam")


def _quiet_rules(count: int) -> str:
    return plural(count, "tipo de teste rodou", "tipos de teste rodaram")


def _time_text(stage: PanelStage) -> str:
    if stage.state in ("pending", "skipped"):
        return STAGE_WORDS[stage.state]
    return fmt_duration(stage.seconds)


def scan_extra(view: PanelView) -> str:
    """Resumo da varredura para o trilho do Resumo: funções e pedidos (ou vazio)."""
    attacked = view.verdict.functions_attacked
    if attacked is None:
        return ""
    text = plural(attacked, "função", "funções")
    if view.traffic is not None and view.traffic.enabled:
        sent = view.traffic.allowed + view.traffic.denied
        text += f", {plural(sent, 'pedido', 'pedidos')}"
    return text


def render_track(view: PanelView, *, extras: bool) -> str:
    """Trilho: largura de cada trecho = tempo da etapa; faixa verde (feita), amarela (cortada)."""
    known = [item.seconds for item in view.stages if item.seconds]
    total = sum(known)
    segments: list[str] = []
    for stage in view.stages:
        width = max(stage.seconds or 0.0, total * _FLOOR) if total else 1.0
        detail = _time_text(stage)
        if extras:
            if stage.key == "scan" and stage.state != "pending" and scan_extra(view):
                detail += f" · {scan_extra(view)}"
            if stage.tokens is not None:
                detail += f" · {fmt_tokens(stage.tokens)}"
        segments.append(
            f'<div class="seg{_SEG_CLASS[stage.state]}" style="flex: {width:.2f} 1 0">'
            f"<b>{h.plain(stage.label)}</b><span>{h.plain(detail)}</span></div>"
        )
    return f'<div class="track">{"".join(segments)}</div>'


def _squares(view: PanelView) -> str:
    done = [item for item in view.functions if item.state in ("tested", "severe")]
    if not done:
        return ""
    severe = sum(1 for item in done if item.state == "severe")
    aria = f"{plural(len(done), 'função atacada', 'funções atacadas')}, {severe} com falha grave"
    if len(done) > _MAX_SQUARES:
        parts = [(float(len(done) - severe), "ok"), (float(severe), "gr")]
        return bar(parts, aria, style="margin: 10px 0 6px")
    size = " sm" if len(done) > _MAX_SQUARES_FULL else ""
    cells = "".join(f'<i class="{"s" if item.state == "severe" else "d"}"></i>' for item in done)
    return (
        f'<div class="grid{size}" style="margin: 10px 0 6px" role="img" '
        f'aria-label="{h.plain(aria)}">{cells}</div>'
    )


def _stage_links(view: PanelView, stage: PanelStage) -> str:
    links: list[str] = []
    if view.commands is not None:
        count = sum(1 for item in view.commands if item.stage == stage.key)
        if count:
            links.append(
                f'<a href="terminal.html">{h.plain(plural(count, "comando", "comandos"))}</a>'
            )
    if stage.key == "probe" and stage.state != "pending":
        links.append('<a href="coverage.html">ver quais ficaram de fora</a>')
    if stage.key == "scan" and stage.state != "pending":
        links.append('<a href="time-and-tokens.html">o que mais demorou</a>')
    if stage.key == "report" and stage.state != "pending":
        links.append('<a href="findings.html">ver as falhas</a>')
    return f'<p class="sm">{" · ".join(links)}</p>' if links else ""


def _stage_block(view: PanelView, number: int, stage: PanelStage, *, last: bool) -> str:
    message = ""
    if stage.message and stage.state == "cut":
        message = f'<p class="sm mu">Mensagem desta etapa:</p>{terminal(stage.message, limit=600)}'
    tokens = (
        fmt_tokens(stage.tokens) + " tokens" if stage.tokens is not None else "— tokens não medidos"
    )
    side = (
        f'<div class="tm"><b>{h.plain(_time_text(stage))}</b>'
        f'<span class="sm mu">{h.plain(tokens)}</span></div>'
    )
    border = ' style="border-bottom: 1px solid var(--ln)"' if last else ""
    grid = _squares(view) if stage.key == "scan" and stage.state != "pending" else ""
    return (
        f'<div class="stg"{border}><span class="nb{_NB_CLASS[stage.state]}">{number}</span>'
        f'<div><b>{h.plain(_TITLES[stage.key])}</b><p class="mu">{h.tagged(stage.summary)}</p>'
        f"{message}{grid}{_stage_links(view, stage)}</div>{side}</div>"
    )


def _stuck(view: PanelView) -> str:
    rows: list[str] = []
    for stage in view.stages:
        if stage.state == "cut":
            reason = h.text(plain_stop_reason(stage.message or _NO_REASON, None), 300)
            rows.append(row("am", f"<b>{h.plain(stage.label)}:</b> parou aqui. {reason}"))
    failed = [item for item in view.functions if item.state == "failed"]
    if failed:
        rows.append(
            row(
                "am",
                f"<b>Alcance:</b> {h.plain(_no_answer(len(failed)))}"
                " como esperado e não foi atacada.",
            )
        )
    if not rows and view.verdict.kind != "finished":
        rows.append(row("am", f"O teste não terminou. {_NO_REASON}", first=True))
    if not rows:
        rows.append(row("ok", "Nada travou: todas as etapas que rodaram terminaram.", first=True))
    note = (
        '<p class="sm mu">Função que não responde no alcance não é atacada: veja a aba '
        "Cobertura.</p>"
    )
    return card(heading("Onde o teste travou") + f"<div>{''.join(rows[:_MAX_TRAVAS])}</div>" + note)


def _rule_rows(view: PanelView) -> str:
    meas = view.measurements
    if not meas.metrics_available:
        return row(
            "no", not_measured("este teste é anterior à medição (sem metrics.json)"), first=True
        )
    with_alerts = [item for item in meas.rules if item.alerts > 0]
    rows = [
        row(
            "am",
            h.ident(item.name),
            end=f'<span class="end">{h.plain(plural(item.alerts, "alerta", "alertas"))}</span>',
            first=index == 0,
        )
        for index, item in enumerate(with_alerts[:_MAX_RULES])
    ]
    quiet = sum(1 for item in meas.rules if item.alerts == 0 and item.completed)
    skipped = sum(1 for item in meas.rules if item.skipped)
    if quiet:
        rows.append(
            row(
                "ok",
                f"{h.plain(_quiet_rules(quiet))} sem alerta.",
                first=not rows,
            )
        )
    if skipped:
        rows.append(
            row(
                "no",
                f"{h.plain(plural(skipped, 'tipo foi pulado', 'tipos foram pulados'))} pelo ZAP.",
            )
        )
    return "".join(rows) or row("no", "Nenhuma regra medida.", first=True)


def render_stages(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Etapas."""
    count = len(view.stages)
    top = card(
        heading(f"As {count} etapas, no tamanho do tempo que levaram")
        + render_track(view, extras=False)
    )
    blocks = "".join(
        _stage_block(view, number, stage, last=number == count)
        for number, stage in enumerate(view.stages, start=1)
    )
    left = card(
        heading("O que aconteceu em cada etapa", style="margin-bottom: 6px") + blocks,
        style="flex: 2.4 1 700px; gap: 0",
    )
    right = (
        '<div style="flex: 1 1 320px; display: flex; flex-direction: column; gap: 16px; '
        'min-width: 0">'
        + _stuck(view)
        + card(heading("Tipos de teste feitos") + f"<div>{_rule_rows(view)}</div>")
        + "</div>"
    )
    return f'{top}\n<div class="g">{left}{right}</div>'
