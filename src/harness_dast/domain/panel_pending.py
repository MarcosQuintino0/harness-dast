"""Página provisória das abas que ainda não foram geradas nesta versão. Módulo puro.

A casca completa e o menu funcionam; só o miolo diz que esta parte do painel ainda não existe.
Quem implementar a aba troca a função de renderização no registro (`panel_pages`).
"""

from harness_dast.domain import html_safe as h
from harness_dast.domain.panel_layout import card
from harness_dast.domain.panel_model import PanelView

PENDING_TEXT = "Esta parte do painel ainda não foi gerada nesta versão"


def render_pending(view: PanelView, title: str) -> str:
    """Miolo provisório de uma aba: o título e a frase de que ela ainda não foi gerada."""
    _ = view
    return card(
        f'<h1 class="big">{h.plain(title)}</h1><p class="mu">{h.plain(PENDING_TEXT)}.</p>'
        '<p class="sm mu">As outras abas do menu continuam funcionando.</p>',
        style="padding: 26px 28px",
    )
