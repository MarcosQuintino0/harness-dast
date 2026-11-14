"""Barras de custo da aba Tempo e tokens (`.cost` e `.cb` do desenho). Módulo puro.

Gráfico de quantidade usa branco (tempo) e cinza (tokens), nunca as cores de estado, e toda
barra leva `role="img"` e `aria-label` com o número por extenso (`system/handoff.html`).
"""

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_format import fmt_duration

_MIN_PERCENT = 1.0


def millis_text(milliseconds: int) -> str:
    """Duração de uma regra: menos de 1 s vira "menos de 1 s" (medido, nunca "0 s")."""
    if milliseconds < 1000:
        return "menos de 1 s"
    return fmt_duration(milliseconds / 1000)


def seconds_text(seconds: float) -> str:
    """Duração medida: abaixo de meio segundo vira "menos de 1 s" (medido, nunca "0 s")."""
    if seconds < 0.5:
        return "menos de 1 s"
    return fmt_duration(seconds)


def cost_bar(fraction: float, text: str, aria: str, *, grey: bool = False) -> str:
    """Barra horizontal com o valor escrito ao lado.

    Args:
        fraction: Largura de 0 a 1 (acima de 1 ou abaixo de 0 é cortada; piso de 1%).
        text: Valor mostrado ao lado (texto nosso).
        aria: Descrição da barra para leitor de tela, JÁ ESCAPADA (`h.plain` para texto nosso,
            `h.ident` ou `h.text` para nome que vem de fora).
        grey: Cinza (tokens) em vez de branco (tempo).
    """
    width = max(min(fraction, 1.0) * 100, _MIN_PERCENT)
    css = ' class="tk"' if grey else ""
    return (
        f'<span class="cb"><i{css} role="img" aria-label="{aria}" '
        f'style="width: {width:.1f}%"></i>{h.plain(text)}</span>'
    )


def share(part: float, whole: float) -> str:
    """Parte de um todo como "68%" (o desenho a usa só ao lado do valor absoluto)."""
    return f"{round(part / whole * 100)}%" if whole > 0 else "—"
