"""Aba Resumo do painel (`summary.html`): deu certo? o que faço agora? Módulo puro.

Fiel a `docs/design/execution-panel/screens/summary.html` e aos estados de
`system/states.html`: com falhas graves, sem falha grave (nunca "seguro"), parou no meio e erro.
Texto nosso sai por `h.plain`; texto do alvo, do OpenAPI, do ZAP ou da CLI sai por `h.text` ou
`h.ident`. Sem número inventado: dado ausente vira traço e "não medido".
"""

from collections import Counter
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_build_content import lead_phrase
from harness_dast.domain.panel_format import (
    NO_DATA,
    fmt_count,
    fmt_date,
    fmt_duration,
    fmt_tokens,
    plural,
    x_of_y,
)
from harness_dast.domain.panel_layout import (
    card,
    chip,
    heading,
    meter,
    owner_row,
    row,
    stat,
)
from harness_dast.domain.panel_model import PanelFinding, PanelView
from harness_dast.domain.panel_stages import render_track

_MAX_ROWS: Final = 8
_WHERE: Final[dict[str, str]] = {
    "preflight": "na conferência",
    "probe": "no alcance",
    "scan": "na varredura",
    "authz": "no teste entre contas",
    "report": "na organização dos achados",
}
_OWNERS: Final = {"qa": "Você (QA)", "owner": "Dono do produto"}
_AFTER_SCAN: Final = ("scan", "authz", "report")


def _fence_clause(view: PanelView) -> str:
    traffic = view.traffic
    if not view.traffic_measured or traffic is None:
        return "A cerca não foi medida nesta execução."
    if traffic.allowed_outside_allow:
        return (
            f"{plural(traffic.allowed_outside_allow, 'pedido passou', 'pedidos passaram')} com "
            "leitura fora do combinado (modo amplo): veja a aba Cobertura."
        )
    return "Nenhum pedido saiu do combinado na carta."


def _where(view: PanelView) -> str:
    key = view.verdict.stopped_stage
    return _WHERE[key] if key else "no meio"


def _reason_text(view: PanelView) -> str:
    verdict = view.verdict
    if verdict.reason:
        return h.text(verdict.reason.rstrip(". "), 300)
    if verdict.stop_requested:
        return "uma pessoa mandou parar"
    return "a execução não registrou o motivo"


def _left_count(view: PanelView) -> int:
    """Funções que não foram atacadas, todas as razões."""
    return sum(1 for item in view.functions if item.state not in ("tested", "severe"))


def _skipped_count(view: PanelView) -> tuple[int, int]:
    """Funções que ficaram de fora por falha ou por não tentadas, e as proibidas pela carta."""
    left = sum(1 for item in view.functions if item.state in ("failed", "not_tried"))
    forbidden = sum(1 for item in view.functions if item.state == "forbidden")
    return left, forbidden


def _hero_text(view: PanelView) -> tuple[str, str, str]:
    """Etiqueta, frase grande e frase de apoio (HTML já escapado)."""
    verdict = view.verdict
    severe = verdict.severe_count
    when = fmt_date(view.identity.started_at)
    if verdict.kind == "partial":
        attacked, tried = verdict.functions_attacked, verdict.functions_attempted
        late = verdict.stopped_stage in _AFTER_SCAN
        count = (
            f", com {x_of_y(attacked, tried)} funções atacadas"
            if late and attacked is not None and tried
            else ""
        )
        seen = (
            f" Até ali apareceu {plural(severe, 'falha grave', 'falhas graves')}."
            if severe is not None
            else ""
        )
        return (
            chip("Parou no meio", "am"),
            f"O teste parou {_where(view)}{count}.",
            f"Motivo: {_reason_text(view)}.{h.plain(seen)} O que faltou não foi testado.",
        )
    if verdict.kind == "error":
        return (
            chip("Erro", "gr"),
            f"O teste deu erro {_where(view)} e nada foi atacado.",
            f"Motivo: {_reason_text(view)}. O que fazer: veja a aba Etapas, corrija a causa e "
            "rode o teste de novo.",
        )
    if not severe:
        attacked = verdict.functions_attacked
        if attacked == 1:
            scope = "na única função testada"
        elif attacked:
            scope = f"nas {fmt_count(attacked)} funções testadas"
        else:
            scope = "no que foi testado"
        left = _left_count(view)
        gap = (
            f"{plural(left, 'função não foi testada', 'funções não foram testadas')} e "
            if left
            else ""
        )
        return (
            chip("Nenhuma falha grave", "ok"),
            f"Nenhuma falha grave {scope}.",
            f"Isto não é um atestado de segurança: {gap}este tipo de teste não vê todo tipo "
            "de falha.",
        )
    strong, weak = verdict.strong_count or 0, verdict.to_confirm_count or 0
    return (
        chip(plural(severe, "falha grave", "falhas graves"), "gr"),
        lead_phrase(strong, weak),
        f"Teste de {when}. Terminou inteiro. {_fence_clause(view)}",
    )


def _stats(view: PanelView) -> str:
    verdict = view.verdict
    attacked, tried = verdict.functions_attacked, verdict.functions_attempted
    if attacked is not None and tried:
        first = stat(x_of_y(attacked, tried), "funções atacadas")
    else:
        first = stat(NO_DATA, "funções atacadas · não medido")
    traffic = view.traffic
    if view.traffic_measured and traffic is not None:
        second = stat(fmt_count(traffic.allowed_outside_allow), "pedidos fora da carta")
    else:
        second = stat(NO_DATA, "pedidos fora da carta · não medido")
    third = stat(
        NO_DATA
        if view.identity.duration_seconds is None
        else fmt_duration(view.identity.duration_seconds),
        "do começo ao fim",
    )
    tokens = view.measurements.tokens_total
    fourth = stat(
        NO_DATA if tokens is None else fmt_tokens(tokens),
        "tokens (agente de IA)" if tokens is not None else "tokens · não medido",
    )
    return f'<div class="stats" style="flex: 1 1 420px">{first}{second}{third}{fourth}</div>'


def _hero(view: PanelView) -> str:
    label, big, sub = _hero_text(view)
    return card(
        '<div class="g" style="gap: 24px 48px; align-items: flex-end">'
        '<div style="flex: 999 1 420px; display: flex; flex-direction: column; gap: 12px">'
        f'<div>{label}</div><h1 class="big">{big}</h1><p class="mu">{sub}</p></div>'
        f"{_stats(view)}</div>",
        style="padding: 26px 28px",
    )


def _finding_title(item: PanelFinding) -> str:
    return item.explanation.title if item.explanation else item.title


def _severe_rows(view: PanelView) -> str:
    severe = view.severe
    if not severe:
        if view.counts is None:
            return row(
                "am",
                "Esta execução não tem <b>findings.json</b>: não há falhas para listar.",
                first=True,
            )
        return row(
            "ok",
            "<b>Nenhuma falha grave.</b> Veja os avisos menores na aba Falhas.",
            end='<a class="end" href="findings.html">avisos</a>',
            first=True,
        )
    if len(severe) > _MAX_ROWS:
        return _grouped_rows(severe)
    rows: list[str] = []
    for item in severe:
        kind = h.text(_finding_title(item), 160)
        # Como no desenho: o título é a função (o que a pessoa conhece); o tipo da falha vai
        # depois do medidor. Sem nome da função, o título é o tipo da falha.
        title = h.text(item.function_name, 160) if item.function_name else kind
        after = f" · {kind}" if item.function_name else ""
        rows.append(
            row(
                "gr" if item.confidence >= 2 else "am",
                f'<b>{title}</b><br><span class="sm mu">{meter(item.confidence)}{after}</span>',
                end=f'<a class="end" href="findings.html#{h.ident(item.finding_id)}">ver prova</a>',
                first=not rows,
            )
        )
    return "".join(rows)


def _grouped_rows(severe: tuple[PanelFinding, ...]) -> str:
    counts = Counter(item.title for item in severe)
    rows = [
        row(
            "gr",
            f"<b>{h.text(title, 160)}</b> · {h.plain(plural(count, 'função', 'funções'))}",
            end='<a class="end" href="findings.html">abrir o grupo</a>',
            first=index == 0,
        )
        for index, (title, count) in enumerate(counts.items())
    ]
    return "".join(rows)


def _minor_line(view: PanelView) -> str:
    counts = view.counts
    if counts is None:
        return ""
    parts = [
        plural(counts.medium, "aviso médio", "avisos médios") if counts.medium else "",
        plural(counts.low, "aviso baixo", "avisos baixos") if counts.low else "",
        plural(counts.informational, "informativo", "informativos") if counts.informational else "",
        plural(
            counts.unknown, "aviso de gravidade desconhecida", "avisos de gravidade desconhecida"
        )
        if counts.unknown
        else "",
    ]
    present = [part for part in parts if part]
    if not present:
        return ""
    joined = ", ".join(present[:-1]) + (" e " if len(present) > 1 else "") + present[-1]
    causes = plural(counts.groups, "causa", "causas")
    return f'<p class="sm mu">{h.plain(f"Mais {joined}, agrupados em {causes}.")}</p>'


def _severe_card(view: PanelView) -> str:
    return card(
        heading("Falhas graves", link=("findings.html", "Abrir todas"))
        + f"<div>{_severe_rows(view)}</div>"
        + _minor_line(view),
        style="flex: 1.15 1 340px",
    )


def _trust_card(view: PanelView) -> str:
    verdict = view.verdict
    rows: list[str] = []
    if verdict.kind == "finished":
        rows.append(
            row(
                "ok",
                "<b>No teste:</b> terminou inteiro",
                end='<a class="end" href="coverage.html">cobertura</a>',
                first=True,
            )
        )
    elif verdict.kind == "partial":
        rows.append(
            row("am", f"<b>No teste:</b> parou no meio, {h.plain(_where(view))}", first=True)
        )
    else:
        rows.append(row("gr", f"<b>No teste:</b> deu erro {h.plain(_where(view))}", first=True))
    if view.functions:
        left, forbidden = _skipped_count(view)
        no_authz = not any(item.key == "authz" and item.state == "done" for item in view.stages)
        text = (
            f"{plural(left, 'função ficou', 'funções ficaram')} de fora"
            if left
            else "nenhuma função ficou de fora"
        )
        if forbidden:
            text += f" (fora as {forbidden} proibidas pela carta)"
        if no_authz:
            text += " e o teste entre contas não rodou"
        rows.append(row("am" if left or no_authz else "ok", f"<b>No teste:</b> {h.plain(text)}"))
    rows.append(_commands_row(view))
    rows.append(_fence_row(view))
    rows.append(_confirm_row(view))
    return card(
        heading("Dá para confiar?") + f"<div>{''.join(rows)}</div>", style="flex: 1 1 300px"
    )


def _commands_row(view: PanelView) -> str:
    if view.commands is None:
        return row(
            "am",
            "<b>No agente:</b> sem diário de comandos para este teste (o diário começou na "
            "versão 1.2)",
        )
    if not view.commands:
        return row(
            "am",
            "<b>No agente:</b> o diário existe, mas não tem comando deste teste",
        )
    total = plural(len(view.commands), "comando", "comandos")
    skipped = (
        "; "
        + plural(
            view.commands_skipped, "linha corrompida foi pulada", "linhas corrompidas foram puladas"
        )
        if view.commands_skipped
        else ""
    )
    return row(
        "am" if view.commands_skipped else "ok",
        f"<b>No agente:</b> {h.plain(total)}, todos visíveis{h.plain(skipped)}",
        end='<a class="end" href="terminal.html">terminal</a>',
    )


def _fence_row(view: PanelView) -> str:
    traffic = view.traffic
    if not view.traffic_measured or traffic is None:
        return row(
            "am", "<b>No agente:</b> pedidos fora da carta não medidos (sem a cerca gerenciada)"
        )
    outside = traffic.allowed_outside_allow
    total = traffic.allowed + traffic.denied
    return row(
        "gr" if outside else "ok",
        f"<b>No agente:</b> {h.plain(x_of_y(outside, total))} pedidos fora da carta",
    )


def _confirm_row(view: PanelView) -> str:
    if view.severe:
        return row("am", "<b>Nas falhas:</b> nenhuma confirmada por pessoa ainda")
    return row("no", "<b>Nas falhas:</b> nenhuma falha grave para confirmar")


def _steps_card(view: PanelView) -> str:
    body = "".join(owner_row(_OWNERS[item.owner], item.text) for item in view.next_steps)
    return card(heading("O que fazer agora") + f"<div>{body}</div>", style="flex: 1.15 1 340px")


def render_summary(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Resumo."""
    track = card(
        heading(
            f"As {len(view.stages)} etapas, no tamanho do tempo que levaram",
            link=("terminal.html", "Ver os comandos"),
        )
        + render_track(view, extras=True)
    )
    return (
        f"{_hero(view)}\n"
        f'<div class="g">{_severe_card(view)}{_trust_card(view)}{_steps_card(view)}</div>\n'
        f"{track}"
    )
