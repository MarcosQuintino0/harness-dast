"""Seção de autorização do `report.md`: achados de origem própria, com a técnica de cada um.

Fica separada dos achados do ZAP: a técnica é a comparação determinística entre contas
(`authz`), a severidade vem da taxonomia do código e nada aqui veio do alvo além de nomes de
campo e códigos HTTP, que passam por `markdown_safe` do mesmo jeito. Este módulo é puro.
"""

from harness_dast.domain.authz_findings import TECHNIQUE_LABEL
from harness_dast.domain.authz_result import AuthzFinding, AuthzResult
from harness_dast.domain.markdown_safe import code_span, escape_inline
from harness_dast.domain.report_labels import CHECK_LABEL, CHECK_STATUS_LABEL, SEVERITY_LABEL

_MAX_NOT_TESTED = 40


def _finding_lines(item: AuthzFinding) -> list[str]:
    accounts = f"conta {code_span(item.actor_account)}"
    if item.actor_role:
        accounts += f" (papel {escape_inline(item.actor_role)})"
    if item.owner_account:
        accounts += f", dona {code_span(item.owner_account)}"
    lines = [
        f"### {code_span(item.finding_id)} {escape_inline(item.title, 160)}",
        "",
        f"- **Técnica:** {escape_inline(TECHNIQUE_LABEL[item.technique])} "
        f"({code_span(item.technique)}), teste de autorização entre contas; não é achado do ZAP.",
        f"- **Severidade proposta pelo código:** {SEVERITY_LABEL[item.proposed_severity]}. "
        "Status: needs_triage.",
        f"- **Onde:** {code_span(f'{item.method} {item.path_template}')}, operação "
        f"{code_span(item.operation_id)}, {accounts}.",
        f"- **Classe:** CWE-{item.cwe}, {escape_inline(item.owasp_api_2023)}.",
    ]
    if item.fields:
        names = ", ".join(code_span(name, 80) for name in item.fields)
        lines.append(f"- **Campos (só nomes; os valores não foram gravados):** {names}.")
    lines += [
        f"- **Fingerprint:** {code_span(item.fingerprint)}.",
        "",
        f"**O que foi observado:** {escape_inline(item.evidence, 600)}",
        "",
        f"**O que significa:** {escape_inline(item.description, 600)}",
        f"**Direção de correção (sugestão genérica):** {escape_inline(item.solution, 400)}",
    ]
    return lines


def authz_lines(authz: AuthzResult | None) -> list[str]:
    """Linhas do Markdown da seção de autorização; vazio quando o estágio não rodou."""
    if authz is None:
        return []
    stop = f" Parada: {escape_inline(authz.stop_message, 300)}" if authz.stop_message else ""
    lines = [
        "## Autorização entre contas (técnica própria, determinística)",
        "",
        f"Estado: {escape_inline(authz.status)}.{stop} Requisições enviadas pelo estágio: "
        f"{authz.requests_sent}. Contas usadas: "
        f"{', '.join(code_span(a) for a in authz.accounts) or 'nenhuma'}.",
        "",
        f"> {escape_inline(authz.notice, 600)}",
        "",
        "| Verificação | Estado | Candidatos | Testados | Achados |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {CHECK_LABEL[row.check]} | {CHECK_STATUS_LABEL[row.status]} | {row.candidates} | "
        f"{row.tested} | {row.findings} |"
        for row in authz.checks
    ]
    if authz.findings:
        lines += ["", "### Achados de autorização", ""]
        for item in authz.findings:
            lines += [*_finding_lines(item), ""]
    else:
        lines += ["", "Nenhum achado de autorização. Leia o que NÃO foi testado antes de concluir."]
    lines += _not_tested_lines(authz)
    lines += ["", "**Limites desta técnica:**", ""]
    lines += [f"- {escape_inline(text, 300)}" for text in authz.limits]
    return lines


def _not_tested_lines(authz: AuthzResult) -> list[str]:
    if not authz.not_tested:
        return []
    lines = ["", "### O que o teste de autorização não pôde testar", ""]
    lines += ["| Verificação | Operação | Motivo | O que fazer |", "|---|---|---|---|"]
    for item in authz.not_tested[:_MAX_NOT_TESTED]:
        where = code_span(f"{item.method} {item.path}") if item.method and item.path else "(geral)"
        lines.append(
            f"| {CHECK_LABEL[item.check]} | {where} | {code_span(item.reason)} | "
            f"{escape_inline(item.message, 200)} |"
        )
    hidden = len(authz.not_tested) - _MAX_NOT_TESTED
    if hidden > 0:
        lines.append(f"\n... e mais {hidden} item(ns); veja `not_tested` em authz.json.")
    return lines
