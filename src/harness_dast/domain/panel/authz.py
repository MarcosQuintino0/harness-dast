"""Aba Autorização: verificações, achados, lacunas e ações sem exigir varredura."""

from harness_dast.domain.panel.layout import card, heading, not_measured
from harness_dast.domain.panel.model import PanelView
from harness_dast.domain.report_html_authz import authz_result_section


def render_authz(view: PanelView) -> str:
    """Mostra resultado e lacunas; ausência do estágio nunca é uma prova de proteção."""
    if view.authz is None:
        return card(
            heading("Autorização entre contas")
            + not_measured(
                "O teste de autorização não rodou; não há conclusão sobre proteção entre contas."
            )
        )
    return card(authz_result_section(view.authz))
