"""Aba Falhas do painel (`findings.html`): o que foi achado e dá para acreditar? Módulo puro.

Fiel a `docs/design/execution-panel/screens/findings.html` e aos estados de
`system/states.html`: falha com prova forte, falha a confirmar, nenhuma falha grave, prova cortada
por ser grande, pedido com corpo (POST) e achado do teste entre contas (sem reprodução à mão).

Uma página só, com uma âncora por falha grave (`findings.html#F-...`): a lista da esquerda e os
links da aba Resumo apontam para elas. Texto nosso sai por `h.plain`; texto do alvo, do ZAP, do
agente ou do OpenAPI sai por `h.text` ou `h.ident`. O medidor de confiança nunca é nota, e a
página nunca diz "seguro" nem "aprovado".
"""

from collections import Counter
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_format import fmt_count, pick, plural
from harness_dast.domain.panel_layout import card, chip, meter, row
from harness_dast.domain.panel_model import PanelFinding, PanelGroup, PanelView
from harness_dast.domain.panel_repro import render_repro

_REPORT: Final = "../report.html"
_MAX_GROUPS: Final = 10
_ZAP_SURE: Final = frozenset({"high", "confirmed"})
_CONFIRM_SENTENCE: Final = (
    "O terceiro degrau (confirmada) só acende quando uma pessoa repete a falha e confirma; este "
    "painel ainda não tem onde registrar a confirmação, por isso nenhuma falha chega lá."
)
_REPEAT_SENTENCE: Final = (
    "Falha a confirmar: a resposta gravada não mostra a falha sozinha (por exemplo, o ataque só "
    "fez o sistema demorar, e demora também acontece por acaso). Repita 3 vezes: se acontecer "
    "sempre, é falha."
)


def _title(item: PanelFinding) -> str:
    return item.explanation.title if item.explanation else item.title


def _label(item: PanelFinding) -> str:
    """O que a pessoa reconhece: a função; sem nome dela, o título da falha."""
    return item.function_name or _title(item)


def _area_of(view: PanelView, item: PanelFinding) -> str | None:
    for function in view.functions:
        if function.operation_id == item.operation_id:
            return function.area
    return None


# ---------------------------------------------------------------- lista da esquerda


def _picks(view: PanelView) -> str:
    if not view.severe:
        return row(
            "ok",
            "<b>Nenhuma falha grave.</b> Veja os avisos menores logo abaixo.",
            end='<a class="end" href="#menores">avisos</a>',
            first=True,
        )
    return "".join(
        f'<a class="pick" href="#{h.ident(item.finding_id)}">'
        f"<b>{h.text(_label(item), 160)}</b>"
        f'<span class="sm mu">{meter(item.confidence)}</span></a>'
        for item in view.severe
    )


def _found(count: int) -> str:
    return plural(count, "achado", "achados")


def _group_label(group: PanelGroup, repeated: frozenset[str]) -> str:
    """Título do grupo; quando outro grupo tem o mesmo título, diz o campo que os separa."""
    if group.title in repeated and group.parameter:
        return f"{group.title} (campo {group.parameter})"
    return group.title


def _group_rows(groups: tuple[PanelGroup, ...]) -> str:
    minor = [group for group in groups if group.severity != "high"]
    shown = minor[:_MAX_GROUPS]
    titles = Counter(group.title for group in minor)
    repeated = frozenset(title for title, count in titles.items() if count > 1)
    rows = [
        row(
            "no",
            h.text(_group_label(group, repeated), 160),
            end=f'<span class="end">{h.plain(_found(group.findings_count))}</span>',
            first=index == 0,
        )
        for index, group in enumerate(shown)
    ]
    if len(minor) > len(shown):
        more = plural(len(minor) - len(shown), "causa", "causas")
        rows.append(row("no", f"Mais {h.plain(more)} no relatório completo."))
    return "".join(rows)


def _minor_card_rows(view: PanelView) -> str:
    counts = view.counts
    if counts is None:
        return ""
    lines = (
        (counts.medium, "Avisos de gravidade média"),
        (counts.low, "Avisos de gravidade baixa"),
        (counts.informational, "Informativos"),
        (counts.unknown, "Avisos de gravidade desconhecida"),
    )
    rows = [
        row("no", h.plain(label), end=f'<span class="end">{fmt_count(value)}</span>')
        for value, label in lines
        if value
    ]
    return "".join(rows)


def _minor_section(view: PanelView) -> str:
    counts = view.counts
    if counts is None:
        return ""
    minor = counts.total - counts.high
    body = _minor_card_rows(view)
    if not minor:
        return (
            '<h2 class="h" id="menores" style="margin-top: 10px">Menores <span>nenhum</span></h2>'
            '<p class="sm mu">Não houve aviso de gravidade menor nesta execução.</p>'
        )
    causes = plural(counts.groups, "causa", "causas")
    return (
        f'<h2 class="h" id="menores" style="margin-top: 10px">Menores · {fmt_count(minor)}</h2>'
        f"<div>{body}</div>"
        f'<p class="sm mu">Reunidos em {h.plain(causes)} (todos os níveis); as principais:</p>'
        f"<div>{_group_rows(view.groups)}</div>"
        f'<p class="sm mu">Quase sempre são os mesmos avisos repetidos em várias funções. '
        f'<a href="{_REPORT}">Relatório completo</a></p>'
    )


def _how_to_read() -> str:
    def bars(level: int) -> str:
        return "".join(f'<i class="{"f" if n < level else ""}"></i>' for n in range(3))

    return (
        '<h2 class="h" style="margin-top: 10px">Como ler a confiança</h2>'
        '<div class="sm mu">'
        f'<p><span class="bars">{bars(1)}</span> a confirmar: a ferramenta desconfia</p>'
        f'<p style="margin-top: 4px"><span class="bars">{bars(2)}</span> prova forte: a '
        "resposta mostra a falha</p>"
        f'<p style="margin-top: 4px"><span class="bars">{bars(3)}</span> confirmada: uma pessoa '
        "repetiu e viu</p></div>"
    )


def _list_card(view: PanelView) -> str:
    return card(
        f'<h2 class="h">Graves · {len(view.severe)}</h2>'
        f"{_picks(view)}{_minor_section(view)}{_how_to_read()}",
        style="flex: 1 1 300px; align-self: flex-start",
    )


# ---------------------------------------------------------------- uma falha grave


def _chips(view: PanelView, item: PanelFinding) -> str:
    chips = [chip("Grave", "gr")]
    area = _area_of(view, item)
    if area:
        chips.append(f'<span class="chip ch-mu">{h.ident(area, 60)}</span>')
    if item.explanation and item.explanation.technical_name:
        technical = h.text(item.explanation.technical_name, 120)
        chips.append(f'<span class="chip ch-mu">Nome técnico: {technical}</span>')
    chips.append(f'<span class="chip ch-mu">{h.ident(item.finding_id, 24)}</span>')
    return f'<div style="display: flex; flex-wrap: wrap; gap: 8px">{"".join(chips)}</div>'


def _where_line(item: PanelFinding) -> str:
    parts = [f"{h.ident(item.method, 12)} {h.ident(item.path_template, 160)}"]
    if item.function_name:
        parts.insert(0, f"Função: <b>{h.text(item.function_name, 120)}</b>")
    if item.parameter:
        vector = f" ({h.text(item.input_vector, 40)})" if item.input_vector else ""
        parts.append(f"onde entrou: {h.text(item.parameter, 80)}{vector}")
    if item.occurrences > 1:
        parts.append(h.plain(plural(item.occurrences, "alerta reunido", "alertas reunidos")))
    return f'<p class="sm mu" style="max-width: 90ch">{" · ".join(parts)}</p>'


def _story(item: PanelFinding) -> str:
    explanation = item.explanation
    if explanation is None:
        text = h.text(item.description, 700) if item.description else "Sem descrição."
        return (
            '<div><h2 class="h" style="margin-bottom: 4px">O que a ferramenta apontou</h2>'
            f'<p class="mu" style="max-width: 72ch">{text}</p></div>'
        )

    def column(title: str, text: str) -> str:
        return (
            '<div style="flex: 1 1 300px; min-width: 0">'
            f'<h2 class="h" style="margin-bottom: 4px">{h.plain(title)}</h2>'
            f'<p class="mu" style="max-width: 72ch">{h.plain(text)}</p></div>'
        )

    return (
        '<div class="g" style="gap: 22px 32px">'
        f"{column('O que aconteceu', explanation.what_happened)}"
        f"{column('Por que importa', explanation.why_it_matters)}</div>"
    )


def _confidence_rows(item: PanelFinding) -> str:
    def line(kind: str, text: str, end: str, *, first: bool = False) -> str:
        return row(kind, h.plain(text), end=f'<span class="end">{h.plain(end)}</span>', first=first)  # type: ignore[arg-type]  # `kind` vem só das chamadas abaixo, sempre um marcador válido

    confirmed = line("no", "Uma pessoa repetiu e confirmou", "ainda não")
    if item.origin == "authz":
        return (
            line(
                "ok",
                "O programa repetiu o pedido com outra conta e comparou as respostas",
                "sim",
                first=True,
            )
            + confirmed
        )
    proven = bool(item.evidence and item.evidence.available and item.evidence.zap_evidence.strip())
    sure = item.proposed_confidence in _ZAP_SURE
    suspect = item.suspected_false_positive
    if suspect is None:
        triage = line("no", "O agente suspeita de falso positivo", "sem triagem")
    elif suspect:
        triage = line("am", "O agente suspeita de falso positivo", "sim")
    elif item.triage_note:
        # O campo diz "não suspeita", mas a nota é texto livre que pode levantar dúvida: sem
        # selo verde, e a nota logo abaixo da linha (não interpretamos a nota).
        triage = line("no", "O agente suspeita de falso positivo", "campo: não suspeita")
    else:
        triage = line("ok", "O agente suspeita de falso positivo", "não suspeita")
    if item.triage_note:
        triage += (
            '<p class="sm mu" style="margin: 4px 0 6px">O agente anotou (texto dele, consultivo): '
            f"{h.text(item.triage_note, 400)}</p>"
        )
    return (
        line(
            "ok" if proven else "no",
            "A resposta gravada mostra a falha",
            "sim" if proven else "não",
            first=True,
        )
        + line(
            "ok" if sure else "no",
            "A ferramenta de ataque, sozinha, já tinha certeza",
            "sim" if sure else "não",
        )
        + triage
        + confirmed
    )


def _confidence_block(item: PanelFinding) -> str:
    notes: list[str] = []
    if item.confidence < 2 and item.origin == "zap":
        notes.append(_REPEAT_SENTENCE)
    notes.append(_CONFIRM_SENTENCE)
    return (
        '<div style="flex: 1 1 300px; min-width: 0">'
        '<h2 class="h" style="margin-bottom: 4px">Confiança nesta falha '
        f"<span>{meter(item.confidence)}</span></h2>"
        f"{_confidence_rows(item)}"
        f'<p class="sm mu" style="margin-top: 8px">{h.plain(" ".join(notes))}</p></div>'
    )


def _actions(item: PanelFinding) -> str:
    explanation = item.explanation
    if explanation and explanation.actions:
        return "".join(
            f'<div class="r"><span class="who">{h.plain(step.who)}</span>'
            f"<span>{h.plain(step.text)}</span></div>"
            for step in explanation.actions
        )
    steps = [
        ("Você (QA)", f"Abrir chamado com o código {item.finding_id} e a prova desta página."),
    ]
    solution = h.text(item.solution, 500) if item.solution else ""
    rows = [
        f'<div class="r"><span class="who">{h.plain(who)}</span>'
        f"<span>{h.text(text, 200)}</span></div>"
        for who, text in steps
    ]
    if solution:
        rows.append(
            f'<div class="r"><span class="who">Time de dev</span><span>{solution}</span></div>'
        )
    return "".join(rows)


def _todo_block(item: PanelFinding) -> str:
    return (
        '<div style="flex: 1 1 300px; min-width: 0">'
        '<h2 class="h" style="margin-bottom: 4px">O que fazer</h2>'
        f"{_actions(item)}</div>"
    )


def _finding_card(view: PanelView, item: PanelFinding) -> str:
    return (
        f'<section class="card" id="{h.ident(item.finding_id)}" '
        'style="gap: 22px; padding: 26px 28px">'
        '<div style="display: flex; flex-direction: column; gap: 10px">'
        f'{_chips(view, item)}<h2 class="big" style="max-width: 30ch">'
        f"{h.text(_title(item), 200)}</h2>{_where_line(item)}</div>"
        f"{_story(item)}"
        f'<div class="g" style="gap: 22px 32px">{_confidence_block(item)}{_todo_block(item)}</div>'
        f"{render_repro(item, view)}</section>"
    )


# ---------------------------------------------------------------- estados sem falha


def _no_severe_card(view: PanelView) -> str:
    counts = view.counts
    tested = view.verdict.functions_attacked
    scope = (
        pick(tested, "na única função testada", f"nas {fmt_count(tested)} funções testadas")
        if tested
        else "no que foi testado"
    )
    return card(
        '<div><span class="chip ch-ok"><i></i>Nenhuma falha grave</span></div>'
        f'<h2 class="big">Nenhuma falha grave {h.plain(scope)}.</h2>'
        '<p class="mu">Isto não é um atestado de segurança: este tipo de teste não vê todo tipo '
        "de falha, e o que ficou de fora está na aba Cobertura. "
        + (
            "Os avisos menores estão na lista ao lado."
            if counts and counts.total
            else "Também não houve aviso menor."
        )
        + "</p>",
        style="padding: 26px 28px",
    )


def _no_report_card() -> str:
    return card(
        '<div><span class="chip ch-am"><i></i>Sem relatório</span></div>'
        '<h1 class="big">Esta execução não tem relatório de falhas.</h1>'
        '<p class="mu">O arquivo <b>findings.json</b> não existe: o teste parou antes do '
        "relatório, ou ele ainda não foi gerado. Não há falha para listar, e isso não quer dizer "
        "que não houve. O que fazer: rode <b>hdast report</b> para este teste e abra esta aba "
        "de novo.</p>",
        style="padding: 26px 28px",
    )


def render_findings(view: PanelView) -> str:
    """Conteúdo do `<main>` da aba Falhas."""
    if view.counts is None:
        return _no_report_card()
    details = "".join(_finding_card(view, item) for item in view.severe)
    right = (
        f'<div style="flex: 3 1 620px; display: flex; flex-direction: column; gap: 16px; '
        f'min-width: 0">{details or _no_severe_card(view)}</div>'
    )
    return f'<h1 class="vh">Falhas</h1><div class="g">{_list_card(view)}{right}</div>'
