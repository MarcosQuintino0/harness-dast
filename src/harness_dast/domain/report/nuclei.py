"""Seção "Nuclei" do `report.md` (ADR 0122). Módulo puro.

Mostra, separado dos achados do ZAP, do `authz` e do `negative`, o que o segundo motor viu: os
achados por gravidade (modelo, método, caminho e contagem), as tecnologias identificadas e os
limites. As tecnologias são só identificação: não viram achado nem entram no gate.

Do valor que um modelo extrai ficam só a contagem e o tamanho em bytes; o conteúdo, a
requisição, a resposta e o `curl-command` nunca existem aqui. Todo texto que veio do alvo ou de
um modelo passa pelo mesmo escape do resto do relatório.
"""

from typing import Final

from harness_dast.domain.markdown_safe import cell_code, code_span, escape_inline
from harness_dast.domain.nuclei_findings import NucleiFinding, TechnologyDetected
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.report.labels import SEVERITY_LABEL, SEVERITY_ORDER

_MAX_FINDINGS: Final = 200
_MAX_TECHNOLOGIES: Final = 100
_TITLE: Final = "## Nuclei (segundo motor, modelos conhecidos de exposição)"
NUCLEI_NOTICE: Final = (
    "O Nuclei roda modelos prontos de um catálogo fixado, atrás de uma cerca própria. A "
    "gravidade vem do código (crítica e alta viram alta; média, média; baixa, baixa; "
    "informativa e desconhecida, informativa) e é uma proposta: todo achado exige triagem "
    "humana. Do valor extraído por um modelo o relatório guarda só a contagem e os bytes. "
    "`hdast confirm` repete o MESMO modelo: isso é reprodução, não confirmação independente, e "
    "a declaração humana segue separada."
)
"""Aviso fixo da seção; serve também ao HTML."""
STATUS_LABEL: Final = {
    "completed": "concluído",
    "stopped_kill": "parado pelo KILL",
    "stopped_window": "parado pela janela",
    "stopped_deadline": "parado pelo prazo",
}
"""Estado do estágio em português."""


def nuclei_summary_lines(by_severity: dict[str, int]) -> list[str]:
    """Tabela de achados do Nuclei por severidade (vazia quando o estágio não rodou)."""
    if not by_severity:
        return []
    lines = ["", "Nuclei (segundo motor, não é do ZAP):", ""]
    lines += ["| Severidade proposta pelo código | Achados |", "|---|---|"]
    lines += [f"| {SEVERITY_LABEL[name]} | {count} |" for name, count in by_severity.items()]
    return lines


def extracted_text(finding: NucleiFinding) -> str:
    """Resumo do valor extraído: contagem e bytes, nunca o conteúdo."""
    record = finding.record
    if record.extracted_count == 0:
        return "nenhum valor extraído"
    return (
        f"{record.extracted_count} valor(es) extraído(s), {record.extracted_bytes} byte(s) no "
        "total (o conteúdo não é gravado)"
    )


def where_text(method: str | None, path: str) -> str:
    """Método e caminho de um resultado (`-` quando o motor não informou o método)."""
    return f"{method or '-'} {path}"


def _finding_lines(item: NucleiFinding) -> list[str]:
    record = item.record
    matcher = f" (verificador {code_span(record.matcher_name, 80)})" if record.matcher_name else ""
    lines = [
        f"#### {code_span(item.finding_id)} {code_span(record.template_id, 120)}",
        "",
        f"- **Severidade proposta pelo código:** {SEVERITY_LABEL[item.proposed_severity]}. "
        "Status: needs_triage.",
        f"- **Modelo:** {code_span(record.template_id, 120)}{matcher}, caminho do modelo "
        f"{code_span(record.template_path, 200)}, tipo {code_span(record.type, 40)}.",
        f"- **Onde:** {code_span(where_text(record.method, record.matched_path), 300)} em "
        f"{code_span(record.host, 120)}.",
        f"- **Ocorrências:** {item.occurrences}. **Valor extraído:** "
        f"{escape_inline(extracted_text(item))}.",
        f"- **Fingerprint:** {code_span(item.fingerprint)}.",
    ]
    triage = item.triage
    if triage is not None:
        suspect = "sim" if triage.suspected_false_positive else "não"
        lines.append(f"- **Triagem (agente, consultiva):** suspeita de falso positivo: {suspect}.")
        if triage.note:
            lines.append(f"  - Nota: {escape_inline(triage.note, 300)}")
        if triage.reason:
            lines.append(f"  - Motivo: {escape_inline(triage.reason, 300)}")
    return lines


def _findings_by_severity(result: NucleiResult) -> list[str]:
    lines: list[str] = []
    shown = 0
    for name in SEVERITY_ORDER:
        group = [item for item in result.findings if item.proposed_severity == name]
        if not group:
            continue
        lines += ["", f"### Gravidade {SEVERITY_LABEL[name].lower()} ({len(group)})", ""]
        for item in group:
            if shown >= _MAX_FINDINGS:
                break
            shown += 1
            lines += [*_finding_lines(item), ""]
    hidden = len(result.findings) - shown
    if hidden > 0:
        lines.append(f"... e mais {hidden} achado(s); veja nuclei.json.")
    return lines


def _technology_row(item: TechnologyDetected) -> str:
    record = item.record
    matcher = cell_code(record.matcher_name, 80) if record.matcher_name else "-"
    where = cell_code(where_text(record.method, record.matched_path), 300)
    return f"| {cell_code(record.template_id, 120)} | {matcher} | {where} |"


def technology_lines(result: NucleiResult) -> list[str]:
    """Tabela "Tecnologias identificadas"; vazia sem tecnologias."""
    if not result.technologies:
        return []
    lines = [
        "",
        "### Tecnologias identificadas (não são achados e não entram no gate)",
        "",
        "| Modelo | Verificador | Onde |",
        "|---|---|---|",
    ]
    lines += [_technology_row(item) for item in result.technologies[:_MAX_TECHNOLOGIES]]
    hidden = len(result.technologies) - _MAX_TECHNOLOGIES
    if hidden > 0:
        lines.append(f"\n... e mais {hidden} tecnologia(s); veja nuclei.json.")
    return lines


def nuclei_lines(result: NucleiResult | None) -> list[str]:
    """Linhas do Markdown da seção; vazio quando o estágio não rodou."""
    if result is None:
        return []
    stop = f" Parada: {escape_inline(result.stop_message, 300)}" if result.stop_message else ""
    login = f"com login da conta {code_span(result.account)}" if result.account else "sem login"
    lines = [
        _TITLE,
        "",
        f"Estado: {escape_inline(STATUS_LABEL[result.status])}.{stop} Nuclei "
        f"{escape_inline(result.nuclei_version, 40)}, modelos "
        f"{escape_inline(result.templates_version, 40)}; {login}; modelos escolhidos: "
        f"{result.templates_selected}.",
        "",
        f"> {escape_inline(NUCLEI_NOTICE, 700)}",
    ]
    if result.excluded:
        reasons = ", ".join(
            f"{escape_inline(reason, 60)}: {count}" for reason, count in result.excluded
        )
        lines += ["", f"Modelos excluídos por motivo: {reasons}."]
    if result.malformed_lines:
        lines += [
            "",
            f"{result.malformed_lines} linha(s) da saída do Nuclei não puderam ser lidas e foram "
            "descartadas: a contagem de achados pode estar abaixo do real.",
        ]
    if result.findings:
        lines += _findings_by_severity(result)
    else:
        lines += [
            "",
            "Nenhum achado do Nuclei. Isso só diz que estes modelos não casaram nestas respostas; "
            "não prova que o produto é seguro.",
        ]
    lines += technology_lines(result)
    return lines
