"""Seção "Valores que o esquema proíbe" do `report.html` (ADR 0051). Módulo puro.

Mesmo conteúdo do `report.md`: contagem por classe e por operação, achados de origem própria,
o que não foi testado e os limites da técnica. Todo texto passa por `html_safe`; o valor enviado
nunca existe aqui (só nome de campo, classe do caso, limite declarado e código HTTP).
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.negative_findings import CLASS_LABEL, TECHNIQUE_LABEL
from harness_dast.domain.negative_result import NegativeFinding, NegativeResult
from harness_dast.domain.report.labels import SEVERITY_LABEL, SEVERITY_ORDER
from harness_dast.domain.report.model import FindingsReport

_MAX_ROWS: Final = 100
_HEAD: Final = (
    "<th>Enviados</th><th>Rejeitados</th><th>Aceitos</th><th>5xx</th><th>Sem conclusão</th>"
)


def negative_cards(report: FindingsReport) -> str:
    """Cartões de achados do estágio por gravidade; vazio quando o estágio não rodou."""
    if report.negative is None:
        return ""
    counts = report.summary.negative_by_severity
    cells = "".join(
        f'<div class="card"><b class="sev-{name}">{counts.get(name, 0)}</b>{SEVERITY_LABEL[name]}'
        "</div>"
        for name in SEVERITY_ORDER
    )
    total = len(report.negative.findings)
    return (
        '<p class="muted">Valores que o esquema proíbe (técnica própria, não é do ZAP):</p>'
        f'<div class="cards">{cells}<div class="card"><b>{total}</b>achado(s) no total</div></div>'
    )


def _status(value: int | None) -> str:
    return "n/d" if value is None else str(value)


def _finding(item: NegativeFinding) -> str:
    sev = item.proposed_severity
    where = "consulta" if item.location == "query" else "corpo JSON"
    restored = (
        ""
        if item.restored is None
        else "<p><b>Restauração do recurso:</b> "
        + ("confirmada." if item.restored else "NÃO confirmada: confira o estado do recurso.")
        + "</p>"
    )
    created = (
        "<p><b>Pode ter criado um recurso com valor inválido</b> (use <code>hdast cleanup</code> "
        "ou o reset do ambiente).</p>"
        if item.created
        else ""
    )
    return (
        f'<article class="group {sev}"><h4>{h.text(item.title, 160)}'
        f'<span class="badge {sev}">{SEVERITY_LABEL[sev]}</span></h4>'
        f'<p class="muted">Técnica: {h.plain(TECHNIQUE_LABEL[item.technique])} '
        f"(<code>{h.plain(item.technique)}</code>). Teste de valores que o esquema proíbe, "
        f"não é achado do ZAP. Achado {h.ident(item.finding_id)}; "
        f"CWE-{item.cwe}, {h.text(item.owasp_api_2023, 120)}.</p>"
        f"<p><b>Onde:</b> <code>{h.ident(item.method + ' ' + item.path_template)}</code>, "
        f"operação {h.ident(item.operation_id)}, conta {h.ident(item.account)}.</p>"
        "<p><b>Campo (só o nome; o valor enviado não foi gravado):</b> "
        f"<code>{h.text(item.field, 80)}</code>, em {where}, caso "
        f"{h.plain(CLASS_LABEL[item.case_class])}; contrato: {h.text(item.declared, 120)}.</p>"
        f"<p><b>Resposta:</b> {_status(item.observed_status)} (com o valor válido, o probe "
        f"recebeu {_status(item.baseline_status)}).</p>"
        f"{restored}{created}"
        f"<p><b>O que foi observado:</b> {h.text(item.evidence, 600)}</p>"
        f"<p><b>O que significa:</b> {h.text(item.description, 600)}</p>"
        "<p><b>Direção de correção (sugestão genérica, não verificada):</b> "
        f"{h.text(item.solution, 400)}</p></article>"
    )


def _counts(negative: NegativeResult) -> str:
    by_class = "".join(
        f"<tr><td>{h.plain(CLASS_LABEL[row.case_class])}</td><td>{row.sent}</td>"
        f"<td>{row.rejected}</td><td>{row.accepted}</td><td>{row.server_error}</td>"
        f"<td>{row.inconclusive}</td></tr>"
        for row in negative.by_class
    )
    table = f"<table><tr><th>Classe do valor</th>{_HEAD}</tr>{by_class}</table>"
    if not negative.operations:
        return table
    by_operation = "".join(
        f"<tr><td><code>{h.ident(row.method + ' ' + row.path)}</code></td><td>{row.sent}</td>"
        f"<td>{row.rejected}</td><td>{row.accepted}</td><td>{row.server_error}</td>"
        f"<td>{row.inconclusive}</td></tr>"
        for row in negative.operations[:_MAX_ROWS]
    )
    extra = len(negative.operations) - _MAX_ROWS
    more = (
        f'<p class="muted">... e mais {extra} operação(ões) (negative.json).</p>'
        if extra > 0
        else ""
    )
    return f"{table}<table><tr><th>Operação</th>{_HEAD}</tr>{by_operation}</table>{more}"


def _not_tested(negative: NegativeResult) -> str:
    if not negative.not_tested:
        return ""
    rows: list[str] = []
    for item in negative.not_tested[:_MAX_ROWS]:
        where = (
            f"<code>{h.ident(item.method + ' ' + item.path)}</code>"
            if item.method and item.path
            else "(geral)"
        )
        field = f"<code>{h.ident(item.field, 80)}</code>" if item.field else "-"
        rows.append(
            f"<tr><td>{where}</td><td>{field}</td><td>{h.ident(item.reason)}</td>"
            f"<td>{h.text(item.message, 200)}</td></tr>"
        )
    extra = len(negative.not_tested) - _MAX_ROWS
    more = (
        f'<p class="muted">... e mais {extra} (veja not_tested em negative.json).</p>'
        if extra > 0
        else ""
    )
    return (
        "<details open><summary>O que o teste de valores proibidos não pôde testar "
        f"({len(negative.not_tested)})</summary><table><tr><th>Operação</th><th>Campo</th>"
        f"<th>Motivo</th><th>O que fazer</th></tr>{''.join(rows)}</table>{more}</details>"
    )


def negative_section(report: FindingsReport) -> str:
    """Seção "Valores que o esquema proíbe"; vazia quando o estágio não rodou."""
    negative = report.negative
    if negative is None:
        return ""
    stop = f" Parada: {h.text(negative.stop_message, 300)}" if negative.stop_message else ""
    accounts = ", ".join(f"<code>{h.ident(name)}</code>" for name in negative.accounts)
    body = (
        "".join(_finding(item) for item in negative.findings[:_MAX_ROWS])
        if negative.findings
        else "<p>Nenhum achado de valor proibido. Leia o que NÃO foi testado antes de concluir.</p>"
    )
    limits = "".join(f"<li>{h.text(text, 300)}</li>" for text in negative.limits)
    created = (
        f'<p class="note"><b>O teste pode ter criado {negative.created_resources} recurso(s) no '
        "ambiente de teste</b> (<code>POST</code> aceito ou com 5xx; <code>DELETE</code> é "
        "proibido). Use <code>hdast cleanup</code> ou o reset do ambiente.</p>"
        if negative.created_resources
        else ""
    )
    return (
        "<h2>Valores que o esquema proíbe (técnica própria, determinística)</h2>"
        f"<p>Estado: {h.ident(negative.status)}.{stop} Requisições enviadas pelo estágio: "
        f"{negative.requests_sent}. Contas usadas: {accounts or 'nenhuma'}.</p>"
        f'<p class="note">{h.text(negative.notice, 600)}</p>{created}{_counts(negative)}{body}'
        f"{_not_tested(negative)}<p><b>Limites desta técnica:</b></p><ul>{limits}</ul>"
    )
