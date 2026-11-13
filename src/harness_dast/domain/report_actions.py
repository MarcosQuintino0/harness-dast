"""Próximos passos ("o que fazer agora") derivados do relatório, em texto nosso. Módulo puro.

A lista é só conselho de leitura. Ela nunca altera severidade, nunca sugere ampliar escopo,
limite, janela ou autorização e sempre termina lembrando que um relatório sem achados não prova
segurança. Aceita achados de qualquer origem e contadores de recusa por qualquer motivo.
"""

from typing import Final

from harness_dast.domain.report_model import FindingsReport

_LOW_REACHABILITY: Final = 0.8


def _count_groups(report: FindingsReport, severity: str) -> tuple[int, int]:
    groups = [item for item in report.groups if item.proposed_severity == severity]
    return len(groups), sum(item.findings_count for item in groups)


def next_steps(report: FindingsReport) -> tuple[str, ...]:
    """Lista, em ordem de importância, o que a pessoa deve fazer ao ler este relatório."""
    steps: list[str] = []
    coverage = report.coverage
    if coverage.partial:
        steps.append(
            "A execução parou antes do fim. O que não foi varrido NÃO deve ser lido como "
            "seguro: refaça a execução depois de tratar a causa da parada, sem ampliar escopo, "
            "limites nem janela sem nova autorização do dono do produto."
        )
    high_groups, high_findings = _count_groups(report, "high")
    if high_groups:
        steps.append(
            f"Confirme primeiro os {high_groups} grupo(s) de gravidade ALTA ({high_findings} "
            "achado(s)): reproduza com o comando de cada grupo e leve ao time de "
            "desenvolvimento. A gravidade é uma proposta do ZAP, não um veredito."
        )
    unknown_groups, _ = _count_groups(report, "unknown")
    if unknown_groups:
        steps.append(
            f"{unknown_groups} grupo(s) têm gravidade desconhecida: leia-os com atenção, a "
            "ferramenta não soube classificá-los."
        )
    other_groups = sum(_count_groups(report, name)[0] for name in ("medium", "low"))
    if other_groups:
        steps.append(f"Planeje a correção dos {other_groups} grupo(s) de gravidade média e baixa.")
    expected = sum(1 for item in report.groups if item.expected_note)
    if expected:
        steps.append(
            f"{expected} grupo(s) têm uma nota de padrão que costuma ser esperado: confirme com "
            "o time se é o caso aqui. O achado continua na lista."
        )
    if coverage.traffic.enabled and coverage.traffic.denied:
        steps.append(
            f"A cerca de escopo recusou {coverage.traffic.denied} pedido(s) do varredor. Veja "
            "a seção de tráfego recusado e confirme com o dono do produto se o escopo da carta "
            "está certo; a ferramenta não o amplia sozinha."
        )
    reach = coverage.reachability_all
    if reach is not None and reach < _LOW_REACHABILITY:
        steps.append(
            f"Só {reach:.0%} das operações do OpenAPI foram alcançadas pelo probe. Ajuste as "
            "regras de dados do perfil e repita, para a varredura cobrir mais."
        )
    if not report.findings:
        steps.append("Nenhum achado não é prova de segurança: leia o que a varredura não cobriu.")
    steps.append(
        "Registre a triagem (o que é falso positivo, o que é real) e gere o relatório de novo."
    )
    return tuple(steps)
