"""Quadros da direita da aba Tempo e tokens: regras do ZAP, funções, lacunas e regras desligadas.

Fiéis a "Tipos de teste que mais demoraram" e "Funções que mais demoraram" de
`docs/design/execution-panel/screens/time-and-tokens.html` (sem a marca "exemplo": os números são
do `metrics.json`). O nome da regra é o que o ZAP dá a ela: texto de fora, sempre escapado. Sem
`metrics.json` (teste anterior à medição) cada quadro mostra o traço e a explicação, nunca zero.
Módulo puro.
"""

from collections import Counter
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_bars import cost_bar, millis_text, seconds_text
from harness_dast.domain.panel_format import fmt_duration, plural, x_of_y
from harness_dast.domain.panel_layout import card, heading, not_measured, row
from harness_dast.domain.panel_model import PanelView

_TOP_RULES: Final = 6
_TOP_FUNCTIONS: Final = 5
_MAX_DISABLED: Final = 8
_MAX_SKIPPED: Final = 6
_OLD_TEST: Final = "este teste é anterior à medição (sem metrics.json)"
_SKIP_REASON: Final[dict[str, str]] = {
    "max_rule_time": "passou do tempo máximo que cada tipo de teste pode gastar",
}
_NO_REASON: Final = "o ZAP não disse o motivo"
_RULE_HEAD: Final = "margin-bottom: 6px"


def _bar_row(label: str, sub: str, fraction: float, text: str) -> str:
    """Linha do desenho: nome à esquerda (com uma frase pequena) e barra com valor à direita."""
    small = f'<br><span class="sm mu">{h.plain(sub)}</span>' if sub else ""
    return (
        f'<div class="r"><span style="flex: 1 1 0">{label}{small}</span>'
        f'<span style="flex: 1 1 0">{cost_bar(fraction, text, f"{label}: {h.plain(text)}")}</span>'
        "</div>"
    )


def _first(body: str) -> str:
    return body.replace('class="r"', 'class="r" style="border-top: 0"', 1)


def _unavailable(view: PanelView, title: str) -> str | None:
    if view.measurements.metrics_available:
        return None
    return card(
        heading(title, style=_RULE_HEAD) + f'<p class="sm">{not_measured(_OLD_TEST)}</p>',
        style="gap: 0",
    )


def _skipped_rules(view: PanelView) -> str:
    """Regras que o ZAP pulou ou interrompeu, com o motivo (do `metrics.json`, por varredura)."""
    found: Counter[tuple[int, str, str, str]] = Counter()
    for operation in view.measurements.operations:
        for rule in operation.rules:
            if rule.state in ("skipped", "interrupted"):
                why = (
                    "ainda rodava quando a varredura terminou"
                    if rule.state == "interrupted"
                    else _SKIP_REASON.get(rule.skip_reason or "", _NO_REASON)
                )
                found[(rule.plugin_id, rule.name, rule.state, why)] += 1
    if not found:
        return ""
    lines = "".join(
        row(
            "am",
            f"<b>{h.ident(name, 80)}</b> "
            f'<span class="mu">{"pulada" if state == "skipped" else "interrompida"}: '
            f"{h.plain(why)} ({h.plain(plural(times, 'varredura', 'varreduras'))})</span>",
            first=index == 0,
        )
        for index, ((_, name, state, why), times) in enumerate(found.most_common(_MAX_SKIPPED))
    )
    more = len(found) - _MAX_SKIPPED
    tail = (
        f'<p class="sm mu">e mais {h.plain(plural(more, "regra", "regras"))}.</p>'
        if more > 0
        else ""
    )
    return f'<p class="sm mu" style="margin-top: 12px">Puladas ou interrompidas:</p>{lines}{tail}'


def render_rules(view: PanelView) -> str:
    """Quadro "Tipos de teste que mais demoraram" (tempo e pedidos por regra do ZAP)."""
    title = "Tipos de teste que mais demoraram"
    if (missing := _unavailable(view, title)) is not None:
        return missing
    meas = view.measurements
    timed = tuple(item for item in meas.rules if item.time_ms > 0)
    if not timed:
        why = "o ZAP não informou o tempo por tipo de teste nesta execução"
        return card(
            heading(title, style=_RULE_HEAD) + f'<p class="sm">{not_measured(why)}</p>',
            style="gap: 0",
        )
    top = timed[:_TOP_RULES]
    biggest = max(item.time_ms for item in top) or 1
    rows = "".join(
        _bar_row(
            h.ident(item.name, 80),
            plural(item.requests, "pedido", "pedidos"),
            item.time_ms / biggest,
            millis_text(item.time_ms),
        )
        for item in top
    )
    note = f"Barra cheia = {millis_text(biggest)} neste quadro."
    partial = (
        f" A soma cobre {x_of_y(meas.rules_measured, meas.rules_measured + meas.rules_unavailable)}"
        " varreduras; as outras ficaram sem a medição por tipo de teste."
        if meas.rules_unavailable
        else ""
    )
    return card(
        heading(title, style=_RULE_HEAD)
        + _first(rows)
        + f'<p class="sm mu" style="margin-top: 8px">{h.plain(note + partial)}</p>'
        + _skipped_rules(view),
        style="gap: 0",
    )


def render_functions(view: PanelView) -> str:
    """Quadro "Funções que mais demoraram" (tempo e pedidos por função varrida)."""
    title = "Funções que mais demoraram"
    if (missing := _unavailable(view, title)) is not None:
        return missing
    names = {item.operation_id: item.name for item in view.functions}
    ordered = sorted(view.measurements.operations, key=lambda item: -item.duration_seconds)
    top = ordered[:_TOP_FUNCTIONS]
    if not top:
        return card(
            heading(title, style=_RULE_HEAD)
            + f'<p class="sm">{not_measured("nenhuma função foi varrida")}</p>',
            style="gap: 0",
        )
    biggest = max(item.duration_seconds for item in top) or 1.0
    rows = "".join(
        _bar_row(
            h.text(names.get(item.operation_id, item.operation_id), 80),
            plural(item.requests, "pedido", "pedidos"),
            item.duration_seconds / biggest,
            seconds_text(item.duration_seconds),
        )
        for item in top
    )
    note = f"Barra cheia = {fmt_duration(biggest)} neste quadro."
    return card(
        heading(title, style=_RULE_HEAD)
        + _first(rows)
        + f'<p class="sm mu" style="margin-top: 8px">{h.plain(note)}</p>',
        style="gap: 0",
    )


def render_gaps(view: PanelView) -> str:
    """Quadro "Lacunas sem tráfego": silêncios em que nenhum pedido passou pela cerca."""
    title = "Lacunas sem tráfego"
    if (missing := _unavailable(view, title)) is not None:
        return missing
    gaps = view.measurements.gaps
    if gaps is None:
        body = f'<p class="sm">{not_measured("sem a auditoria do proxy não há como medir")}</p>'
    elif not gaps.count:
        limit = fmt_duration(gaps.threshold_seconds)
        body = row(
            "ok",
            f"<b>Nenhuma lacuna:</b> o tráfego nunca ficou parado por mais de {limit}.",
            first=True,
        )
    else:
        limit = fmt_duration(gaps.threshold_seconds)
        body = row(
            "am",
            f"<b>{h.plain(plural(gaps.count, 'lacuna', 'lacunas'))} de mais de "
            f"{h.plain(limit)}</b>, "
            f"somando {h.plain(fmt_duration(gaps.total_seconds))}; a maior durou "
            f"{h.plain(fmt_duration(gaps.longest_seconds))}.",
            first=True,
        ) + (
            '<p class="sm mu" style="margin-top: 8px">Lacuna é um silêncio: nenhum pedido passou '
            "pela cerca. Costuma ser um tipo de teste do ZAP esperando resposta de um endereço de "
            "fora, que a cerca nega.</p>"
        )
    return card(heading(title, style=_RULE_HEAD) + body, style="gap: 0")


def render_disabled(view: PanelView) -> str:
    """Quadro "Regras desligadas": o que a política da varredura não rodou, e por quê."""
    title = "Regras desligadas"
    if (missing := _unavailable(view, title)) is not None:
        return missing
    disabled = view.measurements.disabled_rules
    if not disabled:
        body = (
            row("no", "Nenhuma regra desligada.", first=True)
            if view.measurements.operations
            else f'<p class="sm">{not_measured("a varredura não rodou")}</p>'
        )
        return card(heading(title, style=_RULE_HEAD) + body, style="gap: 0")
    lines = "".join(
        row(
            "no",
            f"<b>{h.ident(item.name or f'regra {item.plugin_id}', 80)}</b> "
            f'<span class="mu">{h.text(item.reason, 200)}</span>',
            end='<span class="end">'
            + ("do perfil" if item.source == "profile" else "da ferramenta")
            + "</span>",
            first=index == 0,
        )
        for index, item in enumerate(disabled[:_MAX_DISABLED])
    )
    more = len(disabled) - _MAX_DISABLED
    tail = (
        f'<p class="sm mu" style="margin-top: 8px">e mais '
        f"{h.plain(plural(more, 'regra', 'regras'))}.</p>"
        if more > 0
        else ""
    )
    return card(heading(title, style=_RULE_HEAD) + lines + tail, style="gap: 0")
