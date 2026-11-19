"""Seção "Nuclei" do `report.html` (ADR 0122). Módulo puro.

Mesmo conteúdo do `report.md`: achados por gravidade, tecnologias identificadas (que não são
achados) e limites. Todo texto passa por `html_safe`; do valor extraído só existem a contagem e
os bytes, nunca o conteúdo, a requisição, a resposta ou o `curl-command`.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.nuclei_findings import NucleiFinding, TechnologyDetected
from harness_dast.domain.nuclei_result import NucleiResult
from harness_dast.domain.report.labels import SEVERITY_LABEL, SEVERITY_ORDER
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.report.nuclei import (
    NUCLEI_NOTICE,
    STATUS_LABEL,
    extracted_text,
    where_text,
)

_MAX_FINDINGS: Final = 200
_MAX_TECHNOLOGIES: Final = 100


def nuclei_cards(report: FindingsReport) -> str:
    """Cartões de achados do Nuclei por gravidade; vazio quando o estágio não rodou."""
    if report.nuclei is None:
        return ""
    counts = report.summary.nuclei_by_severity
    cells = "".join(
        f'<div class="card"><b class="sev-{name}">{counts.get(name, 0)}</b>{SEVERITY_LABEL[name]}'
        "</div>"
        for name in SEVERITY_ORDER
    )
    total = len(report.nuclei.findings)
    technologies = len(report.nuclei.technologies)
    return (
        '<p class="muted">Nuclei (segundo motor, não é do ZAP):</p>'
        f'<div class="cards">{cells}<div class="card"><b>{total}</b>achado(s) no total</div>'
        f'<div class="card"><b>{technologies}</b>tecnologia(s) identificada(s)</div></div>'
    )


def _triage(item: NucleiFinding) -> str:
    triage = item.triage
    if triage is None:
        return ""
    suspect = "sim" if triage.suspected_false_positive else "não"
    note = f" Nota: {h.text(triage.note, 300)}" if triage.note else ""
    reason = f" Motivo: {h.text(triage.reason, 300)}" if triage.reason else ""
    return (
        f"<p><b>Triagem (agente, consultiva):</b> suspeita de falso positivo: {suspect}."
        f"{note}{reason}</p>"
    )


def _finding(item: NucleiFinding) -> str:
    record = item.record
    sev = item.proposed_severity
    matcher = (
        f" (verificador <code>{h.text(record.matcher_name, 80)}</code>)"
        if record.matcher_name
        else ""
    )
    return (
        f'<article class="group {sev}"><h4>{h.text(record.template_id, 120)}'
        f'<span class="badge {sev}">{SEVERITY_LABEL[sev]}</span></h4>'
        f'<p class="muted">Achado {h.ident(item.finding_id)}, do Nuclei (não é do ZAP). '
        f"Fingerprint <code>{h.ident(item.fingerprint, 64)}</code>.</p>"
        f"<p><b>Modelo:</b> <code>{h.text(record.template_id, 120)}</code>{matcher}, caminho do "
        f"modelo <code>{h.text(record.template_path, 200)}</code>, tipo "
        f"{h.ident(record.type, 40)}.</p>"
        f"<p><b>Onde:</b> <code>{h.ident(where_text(record.method, record.matched_path), 300)}"
        f"</code> em {h.ident(record.host, 120)}.</p>"
        f"<p><b>Ocorrências:</b> {item.occurrences}. <b>Valor extraído:</b> "
        f"{h.plain(extracted_text(item))}.</p>{_triage(item)}</article>"
    )


def _findings(result: NucleiResult) -> str:
    if not result.findings:
        return (
            "<p>Nenhum achado do Nuclei. Isso só diz que estes modelos não casaram nestas "
            "respostas; não prova que o produto é seguro.</p>"
        )
    out: list[str] = []
    shown = 0
    for name in SEVERITY_ORDER:
        group = [item for item in result.findings if item.proposed_severity == name]
        if not group:
            continue
        out.append(f"<h3>Gravidade {SEVERITY_LABEL[name].lower()} ({len(group)})</h3>")
        for item in group:
            if shown >= _MAX_FINDINGS:
                break
            shown += 1
            out.append(_finding(item))
    hidden = len(result.findings) - shown
    if hidden > 0:
        out.append(f'<p class="muted">... e mais {hidden} achado(s); veja nuclei.json.</p>')
    return "".join(out)


def _technology_row(item: TechnologyDetected) -> str:
    record = item.record
    matcher = f"<code>{h.text(record.matcher_name, 80)}</code>" if record.matcher_name else "-"
    where = h.ident(where_text(record.method, record.matched_path), 300)
    return (
        f"<tr><td><code>{h.text(record.template_id, 120)}</code></td><td>{matcher}</td>"
        f"<td><code>{where}</code></td></tr>"
    )


def _technologies(result: NucleiResult) -> str:
    if not result.technologies:
        return ""
    rows = "".join(_technology_row(item) for item in result.technologies[:_MAX_TECHNOLOGIES])
    hidden = len(result.technologies) - _MAX_TECHNOLOGIES
    more = (
        f'<p class="muted">... e mais {hidden} tecnologia(s); veja nuclei.json.</p>'
        if hidden > 0
        else ""
    )
    return (
        "<h3>Tecnologias identificadas (não são achados e não entram no gate)</h3>"
        "<table><tr><th>Modelo</th><th>Verificador</th><th>Onde</th></tr>"
        f"{rows}</table>{more}"
    )


def nuclei_section(report: FindingsReport) -> str:
    """Seção "Nuclei"; vazia quando o estágio não rodou."""
    result = report.nuclei
    if result is None:
        return ""
    stop = f" Parada: {h.text(result.stop_message, 300)}" if result.stop_message else ""
    login = (
        f"com login da conta <code>{h.ident(result.account)}</code>"
        if result.account
        else "sem login"
    )
    excluded = (
        "<p>Modelos excluídos por motivo: "
        + ", ".join(f"{h.ident(reason, 60)}: {count}" for reason, count in result.excluded)
        + ".</p>"
        if result.excluded
        else ""
    )
    malformed = (
        f'<p class="note">{result.malformed_lines} linha(s) da saída do Nuclei não puderam ser '
        "lidas e foram descartadas: a contagem de achados pode estar abaixo do real.</p>"
        if result.malformed_lines
        else ""
    )
    return (
        "<h2>Nuclei (segundo motor, modelos conhecidos de exposição)</h2>"
        f"<p>Estado: {h.plain(STATUS_LABEL[result.status])}.{stop} Nuclei "
        f"{h.ident(result.nuclei_version, 40)}, modelos {h.ident(result.templates_version, 40)}; "
        f"{login}; modelos escolhidos: {result.templates_selected}.</p>"
        f'<p class="note">{h.plain(NUCLEI_NOTICE)}</p>{excluded}{malformed}'
        f"{_findings(result)}{_technologies(result)}"
    )
