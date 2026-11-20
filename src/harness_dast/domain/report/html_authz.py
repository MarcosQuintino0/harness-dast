"""Seção de autorização entre contas do `report.html`. Módulo puro.

Mostra, separado dos achados do ZAP, o que o estágio `authz` (técnica própria e determinística,
ADR 0027) encontrou: cada achado diz de qual técnica veio, quais contas e qual operação, e a
seção lista o que o estágio NÃO pôde testar e os limites da técnica. Os achados de autorização
não entram em `groups` (ver ADR 0029, adendo): aqui eles são agrupados só na apresentação,
por técnica. Todo texto que pode vir do alvo (nomes de campo, caminhos, mensagens) passa por
`html_safe`; a severidade vem do código e nunca é alterada.
"""

from harness_dast.domain import html_safe as h
from harness_dast.domain.authz.findings import SOURCE_TEXT, TECHNIQUE_LABEL
from harness_dast.domain.authz.owner_plan import visible_authz_notes
from harness_dast.domain.authz.result import AuthzFinding, AuthzNotTested, AuthzResult
from harness_dast.domain.report.authz_matrix import matrix_html
from harness_dast.domain.report.labels import (
    CHECK_LABEL,
    CHECK_STATUS_LABEL,
    SEVERITY_LABEL,
    SEVERITY_ORDER,
)
from harness_dast.domain.report.model import FindingsReport

_MAX_ROWS = 100


def authz_cards(report: FindingsReport) -> str:
    """Cartões de achados de autorização por gravidade; vazio quando o estágio não rodou."""
    if report.authz is None:
        return ""
    counts = report.summary.authz_by_severity
    cells = "".join(
        f'<div class="card"><b class="sev-{name}">{counts.get(name, 0)}</b>{SEVERITY_LABEL[name]}'
        "</div>"
        for name in SEVERITY_ORDER
    )
    total = len(report.authz.findings)
    return (
        '<p class="muted">Autorização entre contas (técnica própria, não é do ZAP):</p>'
        f'<div class="cards">{cells}<div class="card"><b>{total}</b>achado(s) no total</div></div>'
    )


def _who(item: AuthzFinding) -> str:
    who = f"conta {h.ident(item.actor_account)}"
    if item.actor_role:
        who += f" (papel {h.ident(item.actor_role)})"
    if item.owner_account:
        who += f", dona {h.ident(item.owner_account)}"
    return who


def _finding(item: AuthzFinding) -> str:
    sev = item.proposed_severity
    fields = (
        "<p><b>Campos (só nomes; os valores não foram gravados):</b> "
        + ", ".join(f"<code>{h.text(name, 80)}</code>" for name in item.fields)
        + "</p>"
        if item.fields
        else ""
    )
    origin = (
        f"<p><b>Origem do campo testado:</b> {h.text(SOURCE_TEXT[item.candidate_source], 160)}.</p>"
        if item.candidate_source is not None
        else ""
    )
    variants = (
        "<p><b>Variantes de token aceitas (só nomes; o token não foi gravado):</b> "
        + ", ".join(f"<code>{h.text(name, 40)}</code>" for name in item.variants)
        + "</p>"
        if item.variants
        else ""
    )
    return (
        f'<article class="group {sev}"><h4>{h.text(item.title, 160)}'
        f'<span class="badge {sev}">{SEVERITY_LABEL[sev]}</span></h4>'
        f'<p class="muted">Técnica: {h.plain(TECHNIQUE_LABEL[item.technique])} '
        f"(<code>{h.plain(item.technique)}</code>). Teste de autorização entre contas, "
        f"não é achado do ZAP. Achado {h.ident(item.finding_id)}; "
        f"CWE-{item.cwe}, {h.text(item.owasp_api_2023, 120)}.</p>"
        f"<p><b>Onde:</b> <code>{h.ident(item.method + ' ' + item.path_template)}</code>, "
        f"operação {h.ident(item.operation_id)}, {_who(item)}.</p>{fields}{origin}{variants}"
        f"<p><b>O que foi observado:</b> {h.text(item.evidence, 600)}</p>"
        f"<p><b>O que significa:</b> {h.text(item.description, 600)}</p>"
        "<p><b>Direção de correção (sugestão genérica, não verificada):</b> "
        f"{h.text(item.solution, 400)}</p></article>"
    )


def _by_technique(authz: AuthzResult) -> str:
    out: list[str] = []
    for technique, label in TECHNIQUE_LABEL.items():
        items = [item for item in authz.findings if item.technique == technique]
        if items:
            out.append(f"<h4>{h.plain(label)} ({len(items)})</h4>")
            out += [_finding(item) for item in items[:_MAX_ROWS]]
            if len(items) > _MAX_ROWS:
                out.append(
                    f'<p class="muted">... e mais {len(items) - _MAX_ROWS} (authz.json).</p>'
                )
    return "".join(out)


def _checks(authz: AuthzResult) -> str:
    rows = "".join(
        f"<tr><td>{CHECK_LABEL[row.check]}</td><td>{CHECK_STATUS_LABEL[row.status]}</td>"
        f"<td>{row.candidates}</td><td>{row.tested}</td><td>{row.findings}</td></tr>"
        for row in authz.checks
    )
    message = "".join(
        f"<p>{h.text(row.message, 400)}</p>"
        for row in authz.checks
        if row.check == "horizontal" and row.message
    )
    return (
        "<table><tr><th>Verificação</th><th>Estado</th><th>Candidatos</th><th>Testados</th>"
        f"<th>Achados</th></tr>{rows}</table>{message}"
    )


def _where(item: AuthzNotTested) -> str:
    if item.method and item.path:
        return f"<code>{h.ident(item.method + ' ' + item.path)}</code>"
    return "(geral)"


def _not_tested(authz: AuthzResult) -> str:
    if not authz.not_tested:
        return ""
    rows = "".join(
        f"<tr><td>{CHECK_LABEL[item.check]}</td><td>{_where(item)}</td>"
        f"<td>{h.ident(item.reason)}</td><td>{h.text(item.message, 200)}</td></tr>"
        for item in visible_authz_notes(authz.not_tested, _MAX_ROWS)
    )
    extra = len(authz.not_tested) - len(visible_authz_notes(authz.not_tested, _MAX_ROWS))
    more = (
        f'<p class="muted">... e mais {extra} (veja not_tested em authz.json).</p>'
        if extra > 0
        else ""
    )
    return (
        "<details open><summary>O que o teste de autorização não pôde testar "
        f"({len(authz.not_tested)})</summary><table><tr><th>Verificação</th><th>Operação</th>"
        f"<th>Motivo</th><th>O que fazer</th></tr>{rows}</table>{more}</details>"
    )


def authz_section(report: FindingsReport) -> str:
    """Seção "Autorização entre contas"; vazia quando o estágio não rodou."""
    authz = report.authz
    if authz is None:
        return ""
    return authz_result_section(authz)


def authz_result_section(authz: AuthzResult) -> str:
    """Conteúdo comum ao relatório e à aba Autorização, inclusive sem scan ou findings."""
    stop = f" Parada: {h.text(authz.stop_message, 300)}" if authz.stop_message else ""
    accounts = ", ".join(f"<code>{h.ident(name)}</code>" for name in authz.accounts) or "nenhuma"
    body = (
        _by_technique(authz)
        if authz.findings
        else "<p>Nenhum achado de autorização. Leia o que NÃO foi testado antes de concluir.</p>"
    )
    limits = "".join(f"<li>{h.text(text, 300)}</li>" for text in authz.limits)
    created = (
        f'<p class="note"><b>O teste criou {authz.created_resources} recurso(s) no ambiente de '
        "teste</b> (<code>POST</code> da atribuição em massa; <code>DELETE</code> é proibido). "
        "Use <code>hdast cleanup</code> ou o reset do ambiente.</p>"
        if authz.created_resources
        else ""
    )
    return (
        "<h2>Autorização entre contas (técnica própria, determinística)</h2>"
        f"<p>Estado: {h.ident(authz.status)}.{stop} Requisições enviadas pelo estágio: "
        f"{authz.requests_sent}. Contas usadas: {accounts}.</p>"
        f'<p class="note">{h.text(authz.notice, 600)}</p>{created}{_checks(authz)}'
        f"{matrix_html(authz.access_matrix)}{body}"
        f"{_not_tested(authz)}<p><b>Limites desta técnica:</b></p><ul>{limits}</ul>"
    )
