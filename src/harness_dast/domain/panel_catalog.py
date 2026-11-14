"""Do catálogo de explicação de falhas para o gancho `explanations` do painel. Módulo puro.

O catálogo (`finding_explain`) tem o texto fixo por tipo de falha; aqui ele vira `PanelExplanation`
(o que a aba Falhas desenha), uma por `finding_id`. O texto é nosso e nunca vem do alvo; só um
tipo desconhecido ecoa o nome da regra do ZAP (limpo e cortado pelo próprio catálogo). Nada aqui
altera severidade, confiança ou status do achado.
"""

from typing import Final

from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.finding_explain import (
    FindingExplanation,
    Who,
    explain_authz_technique,
    explain_finding,
)
from harness_dast.domain.panel_model import PanelAction, PanelExplanation
from harness_dast.domain.report_model import FindingsReport

_WHO_LABELS: Final[dict[Who, str]] = {
    "QA": "Você (QA)",
    "dono do produto": "Dono do produto",
    "time de desenvolvimento": "Time de dev",
}


def who_label(who: Who) -> str:
    """Como a tela escreve quem faz o passo (`QA` vira `Você (QA)`)."""
    return _WHO_LABELS[who]


def to_panel_explanation(entry: FindingExplanation) -> PanelExplanation:
    """Converte uma entrada do catálogo no que a aba Falhas desenha."""
    actions = tuple(
        PanelAction(who=who_label(step.who), text=step.text) for step in entry.what_to_do
    )
    return PanelExplanation(
        title=entry.title,
        technical_name=entry.technical_name,
        what_happened=entry.what_happened,
        why_it_matters=entry.why_it_matters,
        what_to_do=" ".join(step.text for step in entry.what_to_do),
        who=who_label(entry.who),
        actions=actions,
    )


def build_explanations(
    report: FindingsReport | None, authz: AuthzResult | None
) -> dict[str, PanelExplanation]:
    """Explicação por `finding_id` de todos os achados do ZAP e do teste entre contas.

    Args:
        report: `findings.json`, ou `None`.
        authz: `authz.json`, ou `None`.

    Returns:
        Um dicionário vazio quando não há achado; nunca levanta por tipo desconhecido (ele recebe
        a explicação genérica e honesta do catálogo).
    """
    found = {
        item.finding_id: to_panel_explanation(explain_finding(item))
        for item in (report.findings if report else ())
    }
    for item in authz.findings if authz else ():
        found[item.finding_id] = to_panel_explanation(explain_authz_technique(item.technique))
    return found
