"""Seção "Valores que o esquema proíbe" do `report.md` (ADR 0051). Módulo puro.

Mostra, separado dos achados do ZAP e do `authz`, o que o estágio `negative` (técnica própria,
determinística) viu: por operação, quantos casos foram enviados, quantos o servidor rejeitou (o
esperado), quantos aceitou e quantos deram 5xx; os achados; o que não foi testado e os limites.
Nada aqui é o valor enviado nem corpo de resposta: só nomes de campo, a classe do caso, o limite
declarado no contrato e códigos HTTP, que passam pelo mesmo escape do resto do relatório.
"""

from typing import Final

from harness_dast.domain.markdown_safe import cell_code, code_span, escape_inline
from harness_dast.domain.negative_findings import CLASS_LABEL, TECHNIQUE_LABEL
from harness_dast.domain.negative_result import NegativeFinding, NegativeResult
from harness_dast.domain.report.labels import SEVERITY_LABEL

_MAX_NOT_TESTED: Final = 40
_MAX_FINDINGS: Final = 200
_TITLE: Final = "## Valores que o esquema proíbe (técnica própria, determinística)"
_COUNT_COLUMNS: Final = "| Enviados | Rejeitados | Aceitos | 5xx | Sem conclusão |"


def negative_summary_lines(by_severity: dict[str, int]) -> list[str]:
    """Tabela de achados do estágio por severidade (vazia quando o estágio não rodou)."""
    if not by_severity:
        return []
    lines = ["", "Valores que o esquema proíbe (técnica própria, não é do ZAP):", ""]
    lines += ["| Severidade proposta pelo código | Achados |", "|---|---|"]
    lines += [f"| {SEVERITY_LABEL[name]} | {count} |" for name, count in by_severity.items()]
    return lines


def _status(value: int | None) -> str:
    return "n/d" if value is None else str(value)


def _finding_lines(item: NegativeFinding) -> list[str]:
    where = "consulta" if item.location == "query" else "corpo JSON"
    lines = [
        f"### {code_span(item.finding_id)} {escape_inline(item.title, 160)}",
        "",
        f"- **Técnica:** {escape_inline(TECHNIQUE_LABEL[item.technique])} "
        f"({code_span(item.technique)}), teste de valores que o esquema proíbe; não é achado do "
        "ZAP.",
        f"- **Severidade proposta pelo código:** {SEVERITY_LABEL[item.proposed_severity]}. "
        "Status: needs_triage.",
        f"- **Onde:** {code_span(f'{item.method} {item.path_template}')}, operação "
        f"{code_span(item.operation_id)}, conta {code_span(item.account)}.",
        f"- **Campo (só o nome; o valor enviado não foi gravado):** {code_span(item.field, 80)}, "
        f"em {where}, caso {escape_inline(CLASS_LABEL[item.case_class])}; contrato: "
        f"{escape_inline(item.declared, 120)}.",
        f"- **Resposta:** {_status(item.observed_status)} (com o valor válido, o probe "
        f"recebeu {_status(item.baseline_status)}).",
        f"- **Classe:** CWE-{item.cwe}, {escape_inline(item.owasp_api_2023)}.",
    ]
    if item.restored is not None:
        lines.append(
            "- **Restauração do recurso:** "
            + ("confirmada." if item.restored else "NÃO confirmada: confira o estado do recurso.")
        )
    if item.created:
        lines.append(
            "- **Pode ter criado um recurso com valor inválido** (use `hdast cleanup` ou o "
            "reset do ambiente)."
        )
    lines += [
        f"- **Fingerprint:** {code_span(item.fingerprint)}.",
        "",
        f"**O que foi observado:** {escape_inline(item.evidence, 600)}",
        "",
        f"**O que significa:** {escape_inline(item.description, 600)}",
        f"**Direção de correção (sugestão genérica):** {escape_inline(item.solution, 400)}",
    ]
    return lines


def _count_lines(negative: NegativeResult) -> list[str]:
    lines = [f"| Classe do valor {_COUNT_COLUMNS}", "|---|---|---|---|---|---|"]
    lines += [
        f"| {escape_inline(CLASS_LABEL[row.case_class])} | {row.sent} | {row.rejected} | "
        f"{row.accepted} | {row.server_error} | {row.inconclusive} |"
        for row in negative.by_class
    ]
    if negative.operations:
        lines += ["", f"| Operação {_COUNT_COLUMNS}", "|---|---|---|---|---|---|"]
        lines += [
            f"| {cell_code(f'{row.method} {row.path}')} | {row.sent} | {row.rejected} | "
            f"{row.accepted} | {row.server_error} | {row.inconclusive} |"
            for row in negative.operations
        ]
    return lines


def _not_tested_lines(negative: NegativeResult) -> list[str]:
    if not negative.not_tested:
        return []
    lines = ["", "### O que o teste de valores proibidos não pôde testar", ""]
    lines += ["| Operação | Campo | Motivo | O que fazer |", "|---|---|---|---|"]
    for item in negative.not_tested[:_MAX_NOT_TESTED]:
        where = cell_code(f"{item.method} {item.path}") if item.method and item.path else "(geral)"
        field = cell_code(item.field, 80) if item.field else "-"
        lines.append(
            f"| {where} | {field} | {cell_code(item.reason)} | {escape_inline(item.message, 200)} |"
        )
    hidden = len(negative.not_tested) - _MAX_NOT_TESTED
    if hidden > 0:
        lines.append(f"\n... e mais {hidden} item(ns); veja `not_tested` em negative.json.")
    return lines


def negative_lines(negative: NegativeResult | None) -> list[str]:
    """Linhas do Markdown da seção; vazio quando o estágio não rodou."""
    if negative is None:
        return []
    stop = f" Parada: {escape_inline(negative.stop_message, 300)}" if negative.stop_message else ""
    lines = [
        _TITLE,
        "",
        f"Estado: {escape_inline(negative.status)}.{stop} Requisições enviadas pelo estágio: "
        f"{negative.requests_sent}. Contas usadas: "
        f"{', '.join(code_span(a) for a in negative.accounts) or 'nenhuma'}.",
        "",
        f"> {escape_inline(negative.notice, 600)}",
        "",
    ]
    if negative.created_resources:
        lines += [
            f"**O teste pode ter criado {negative.created_resources} recurso(s) no ambiente de "
            "teste** (`POST` aceito ou com 5xx; `DELETE` é proibido). Use `hdast cleanup` ou o "
            "reset do ambiente.",
            "",
        ]
    lines += _count_lines(negative)
    if negative.findings:
        lines += ["", "### Achados de valores que o esquema proíbe", ""]
        for item in negative.findings[:_MAX_FINDINGS]:
            lines += [*_finding_lines(item), ""]
        hidden = len(negative.findings) - _MAX_FINDINGS
        if hidden > 0:
            lines.append(f"... e mais {hidden} achado(s); veja negative.json.")
    else:
        lines += [
            "",
            "Nenhum achado de valor proibido. Leia o que NÃO foi testado antes de concluir.",
        ]
    lines += _not_tested_lines(negative)
    lines += ["", "**Limites desta técnica:**", ""]
    lines += [f"- {escape_inline(text, 300)}" for text in negative.limits]
    return lines
