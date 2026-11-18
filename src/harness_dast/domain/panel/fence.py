"""Quadro "A cerca" da aba Cobertura: quantos pedidos passaram, quantos foram barrados e por quê.

Fiel ao painel "A cerca" de `docs/arquivo/design/execution-panel/screens/coverage.html` e aos
estados "modo amplo" e "tráfego não medido" de `system/states.html`. Os motivos vêm dos rótulos de
`scope_labels` (nunca duplicados aqui) e o aviso de cobertura parcial é o de `report_traffic`.
Sem a auditoria do proxy não há como saber quantos pedidos foram barrados: o quadro mostra o
traço e a explicação, nunca zero. Módulo puro.
"""

import re
from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel.format import NO_DATA, fmt_count, pick, plural, x_of_y
from harness_dast.domain.panel.layout import card, chip, not_measured
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.report.traffic import denied_rows, path_shape_warning
from harness_dast.domain.scope_reason import ScopeReason
from harness_dast.domain.traffic import TrafficSummary

_LEGACY_SHAPE: Final = "malformed_request"
_MAX_REASONS: Final = 8
_MODE_WORD: Final = {"strict": "modo estrito", "wide": "modo amplo"}
_EXPLAIN: Final = (
    "Modo estrito: só passa endereço escrito de forma simples e dentro do que a carta combinou. "
    "Modo amplo (só se a carta autorizar): também deixa passar endereço disfarçado, que o "
    "servidor pode ler de outro jeito."
)
_NO_FENCE: Final = "a cerca não foi medida: a execução não tem scan.json"
_NO_AUDIT: Final = (
    "sem a auditoria do proxy (pilha gerenciada) não dá para dizer quantos pedidos foram barrados"
)


def _kind(code: str) -> str:
    """Em qual grupo cai um motivo de recusa: `shape`, `outside` ou `other`."""
    if code == _LEGACY_SHAPE:
        return "shape"
    try:
        reason = ScopeReason(code)
    except ValueError:
        return "other"
    return "shape" if reason.is_malformed else "outside"


def split_denied(traffic: TrafficSummary) -> dict[str, int]:
    """Barrados por grupo (`shape`, `outside`, `other`), usando o motivo mais detalhado que há."""
    source = traffic.denied_by_detail or traffic.denied_by_reason
    groups = {"shape": 0, "outside": 0, "other": 0}
    for code, count in source.items():
        groups[_kind(code)] += count
    groups["other"] += max(traffic.denied - sum(groups.values()), 0)
    return groups


def _stack(parts: tuple[tuple[int, str, str], ...], aria: str) -> str:
    """Barra de 16 px do desenho: passou (verde), forma do endereço (cinza), fora (hachurado).

    Cada parte é (pedidos, classe, cor de fundo); a cor vazia deixa a classe pintar.
    """
    total = sum(count for count, _, _ in parts) or 1
    cells = ""
    for count, css, color in parts:
        if count <= 0:
            continue
        klass = f' class="{css}"' if css else ""
        paint = f"; background: var(--{color})" if color else ""
        cells += f'<i{klass} style="width: {count / total * 100:.2f}%{paint}"></i>'
    return f'<div class="stack" role="img" aria-label="{h.plain(aria)}">{cells}</div>'


def _line(mark: str, text: str, value: str) -> str:
    return f'<div class="r">{mark}<span>{text}</span><span class="end">{value}</span></div>'


def _rows(traffic: TrafficSummary, wide: bool) -> str:
    groups = split_denied(traffic)
    outside = fmt_count(traffic.allowed_outside_allow)
    hatch = '<i class="dotk b-hatch" style="border: 1px solid var(--mu)"></i>'
    grey = '<i class="dotk" style="background: var(--mu)"></i>'
    rows = [
        _line(
            '<i class="dotk k-ok"></i>',
            "Passaram e chegaram ao sistema",
            fmt_count(traffic.allowed),
        ),
        _line(grey, "Barrados: endereço disfarçado", fmt_count(groups["shape"])),
        _line(hatch, "Barrados: apontavam para fora", fmt_count(groups["outside"])),
    ]
    if groups["other"]:
        rows.append(_line(grey, "Barrados: outros motivos", fmt_count(groups["other"])))
    if wide:
        rows.append(
            _line(
                '<i class="dotk k-am"></i>',
                "<b>Endereço disfarçado: decifrados e passaram</b>",
                f"<b>{h.plain(outside)}</b>",
            )
        )
    else:
        rows.append(
            _line(
                '<i class="dotk k-no"></i>',
                "<b>Chegaram a lugar proibido</b>",
                f'<b style="color: var(--ink)">{h.plain(outside)}</b>',
            )
        )
    return f"<div>{''.join(rows)}</div>"


_CODE_IN_LABEL: Final = re.compile(r"\s*\(([a-z_]+(?:\.[a-z_]+)*)\)$")


def _reason_label(label: str, code: str) -> str:
    """A frase simples primeiro; o termo do perfil e o código da auditoria, em etiquetas."""
    found = _CODE_IN_LABEL.search(label)
    phrase = label[: found.start()] if found else label
    tags = [found.group(1)] if found else []
    chips = "".join(f' <span class="chip ch-mu">{h.ident(tag)}</span>' for tag in (*tags, code))
    return f"{h.ident(phrase)}{chips}"


def _reasons(traffic: TrafficSummary) -> str:
    """Os motivos em detalhe: o nome em português e, ao lado, o código da auditoria."""
    rows = denied_rows(traffic)
    if not rows:
        return ""
    shown = "".join(
        f'<div class="r"><span>{_reason_label(label, code)}</span>'
        f'<span class="end">{h.plain(fmt_count(count))}</span></div>'
        for label, code, count in rows[:_MAX_REASONS]
    )
    more = len(rows) - _MAX_REASONS
    tail = (
        f'<p class="sm mu">e mais {h.plain(plural(more, "motivo menor", "motivos menores"))}.</p>'
        if more > 0
        else ""
    )
    return (
        '<p class="sm mu" style="margin-top: 4px">Os motivos, em detalhe:</p>'
        f"<div>{shown}</div>{tail}"
    )


def _partial_notice(traffic: TrafficSummary, *, strict: bool) -> str:
    """Aviso de cobertura parcial (o mesmo caso de `report_traffic`), em português simples.

    Aparece quando a cerca barrou pedidos pela forma do caminho: os ataques que dependem dessas
    formas não chegaram ao sistema. Os motivos exatos ficam na lista em detalhe, logo abaixo.
    """
    if not path_shape_warning(traffic):
        return ""
    total = traffic.allowed + traffic.denied
    advice = (
        " Só o dono do produto pode autorizar o modo amplo na carta; o agente não o liga."
        if strict
        else ""
    )
    text = (
        f"{x_of_y(traffic.path_shape_denied, total)} "
        f"{pick(total, 'pedido foi barrado', 'pedidos foram barrados')} pela forma do "
        "endereço. Os ataques que dependem dessas formas não chegaram ao sistema: a cobertura "
        f"de injeção em caminho foi parcial.{advice}"
    )
    return (
        '<div class="r"><i class="dotk k-am"></i><span><b>Cobertura parcial.</b> '
        f'<span class="mu">{h.plain(text)}</span></span></div>'
    )


def _heading(view: PanelView) -> str:
    mode = view.identity.fence_mode
    badge = chip(_MODE_WORD.get(mode, mode), "run", dot=False) if mode else ""
    return f'<h2 class="h">A cerca {badge}</h2>'


def _measured(view: PanelView, traffic: TrafficSummary) -> str:
    total = traffic.allowed + traffic.denied
    groups = split_denied(traffic)
    wide = view.identity.fence_mode == "wide"
    parts = (
        (traffic.allowed, "", "ok"),
        (groups["shape"], "", "mu"),
        (groups["outside"] + groups["other"], "b-hatch", ""),
    )
    aria = (
        f"{fmt_count(traffic.allowed)} passaram, {fmt_count(groups['shape'])} barrados pela forma "
        f"do endereço, {fmt_count(groups['outside'] + groups['other'])} barrados por apontar para "
        "fora ou por outro motivo"
    )
    intro = (
        '<p class="sm mu">A cerca é a trava que confere cada pedido antes de ele sair. Barrar é '
        f"ela funcionando, não um problema. Dos {h.plain(fmt_count(total))} que o teste tentou "
        "mandar:</p>"
    )
    return (
        intro
        + _stack(parts, aria)
        + _rows(traffic, wide)
        + _partial_notice(traffic, strict=view.identity.fence_mode == "strict")
        + _reasons(traffic)
        + f'<p class="sm mu">{h.plain(_EXPLAIN)}</p>'
    )


def render_fence(view: PanelView) -> str:
    """Quadro "A cerca": o que passou, o que foi barrado e por quê (traço se não foi medido)."""
    traffic = view.traffic
    if traffic is None:
        body = (
            f'<p class="sm">{not_measured(_NO_FENCE)}</p><p class="sm mu">{h.plain(_EXPLAIN)}</p>'
        )
    elif not view.traffic_measured:
        body = (
            f'<p class="sm">{not_measured(_NO_AUDIT)}</p>'
            f'<div class="r"><span>Pedidos barrados</span><span class="end">{NO_DATA}</span></div>'
            f'<p class="sm mu">{h.plain(_EXPLAIN)}</p>'
        )
    else:
        body = _measured(view, traffic)
    return card(_heading(view) + body)
