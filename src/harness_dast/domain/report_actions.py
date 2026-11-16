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


def _has_own_findings(report: FindingsReport) -> bool:
    return bool(
        report.findings
        or (report.authz and report.authz.findings)
        or (report.negative and report.negative.findings)
    )


def _authz_steps(report: FindingsReport) -> list[str]:
    authz = report.authz
    if authz is None:
        return []
    steps: list[str] = []
    counts = report.summary.authz_by_severity
    if authz.status != "completed":
        steps.append(
            "O teste de autorização entre contas parou antes do fim: o que ele não comparou NÃO "
            "deve ser lido como seguro. Veja o estado e a parada na seção de autorização."
        )
    if counts.get("high"):
        steps.append(
            f"Confirme os {counts['high']} achado(s) de autorização entre contas de gravidade "
            "ALTA (acesso a dado de outra conta, função de papel maior ou campo que não devia "
            "ser aceito): cada um diz a técnica, as contas e a operação. A severidade vem da "
            "regra do código, não é um veredito."
        )
    rest = sum(counts.get(name, 0) for name in ("medium", "low", "informational", "unknown"))
    if rest:
        steps.append(f"Leia também os {rest} achado(s) de autorização de gravidade menor.")
    if authz.not_tested:
        steps.append(
            f"O teste de autorização não pôde testar {len(authz.not_tested)} item(ns) (por "
            "exemplo, falta de uma segunda conta do mesmo papel ou de authz.role_order no "
            "perfil). Leia a tabela de motivos: a ausência de achado nesses itens não prova "
            "nada."
        )
    return steps


def _negative_steps(report: FindingsReport) -> list[str]:
    negative = report.negative
    if negative is None:
        return []
    steps: list[str] = []
    counts = report.summary.negative_by_severity
    if negative.status != "completed":
        steps.append(
            "O teste de valores que o esquema proíbe parou antes do fim: o que ele não enviou "
            "NÃO deve ser lido como validado. Veja o estado e a parada na seção dele."
        )
    found = sum(counts.values())
    if found:
        steps.append(
            f"Triar os {found} achado(s) de valores que o esquema proíbe: cada um diz o campo, a "
            "classe do valor e a resposta. Aceitar pode ser coerção legítima e 5xx pode vir do "
            "estado do alvo; a severidade vem da regra do código, não é um veredito."
        )
    if negative.created_resources:
        steps.append(
            f"O teste de valores proibidos pode ter deixado {negative.created_resources} "
            "recurso(s) no ambiente de teste: peça a uma pessoa para rodar `hdast cleanup` (ou "
            "o reset do ambiente)."
        )
    if negative.not_tested:
        steps.append(
            f"O teste de valores proibidos não pôde testar {len(negative.not_tested)} item(ns) "
            "(escrita sem a carta, orçamento, esquema que o código não confirma...). Leia a "
            "tabela de motivos: a ausência de achado neles não prova nada."
        )
    return steps


def next_steps(report: FindingsReport) -> tuple[str, ...]:
    """Lista, em ordem de importância, o que a pessoa deve fazer ao ler este relatório."""
    steps: list[str] = []
    coverage = report.coverage
    if coverage.partial:
        steps.append(
            "A cobertura tem lacunas ou não pôde ser comprovada. O que não foi coberto NÃO "
            "deve ser lido como seguro: consulte os motivos e, após tratar a causa, refaça a "
            "execução sem ampliar escopo, limites nem janela sem nova autorização do dono do "
            "produto."
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
    steps += _authz_steps(report)
    steps += _negative_steps(report)
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
        backoff = coverage.traffic.denied_by_reason.get("rate_backoff", 0)
        backoff_note = (
            f" Desses, {backoff} foram recusados durante o recuo temporário."
            if 0 < backoff <= coverage.traffic.denied
            else ""
        )
        steps.append(
            f"O proxy recusou {coverage.traffic.denied} pedido(s) do varredor.{backoff_note} "
            "Veja a seção de tráfego recusado para conferir os motivos e, se necessário, confirme "
            "com o dono do produto se o escopo da carta está certo; a ferramenta não o amplia "
            "sozinha."
        )
    reach = coverage.reachability_all
    if reach is not None and reach < _LOW_REACHABILITY:
        steps.append(
            f"Só {reach:.0%} das operações do OpenAPI foram alcançadas pelo probe. Ajuste as "
            "regras de dados do perfil e repita, para a varredura cobrir mais."
        )
    if not _has_own_findings(report):
        steps.append("Nenhum achado não é prova de segurança: leia o que a varredura não cobriu.")
    steps.append(
        "Registre a triagem (o que é falso positivo, o que é real) e gere o relatório de novo."
    )
    return tuple(steps)
