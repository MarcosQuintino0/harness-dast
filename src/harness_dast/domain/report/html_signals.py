"""Seção "Sinais vistos pela cerca" do `report.html` (ADR 0049). Módulo puro.

Mesmo conteúdo do `report.md`: respostas lidas, não lidas (com o motivo), com sinal e os achados
de origem própria. Todo texto passa por `html_safe`; nada vem do corpo de uma resposta.
"""

from typing import Final

from harness_dast.domain import html_safe as h
from harness_dast.domain.error_signal_catalog import RULE_BY_CATEGORY
from harness_dast.domain.report.labels import SEVERITY_LABEL
from harness_dast.domain.report.signals import skipped_text
from harness_dast.domain.signal_result import ProxySignals, SignalFinding

_MAX_ROWS: Final = 200


def _finding(item: SignalFinding) -> str:
    sev = item.proposed_severity
    where = f"<code>{h.ident(item.method + ' ' + item.path_template)}</code>"
    if item.operation_id:
        where += f", operação {h.ident(item.operation_id)}"
    params = (
        "<p><b>Parâmetros de consulta (só nomes):</b> "
        + ", ".join(f"<code>{h.ident(name, 80)}</code>" for name in item.query_params)
        + "</p>"
        if item.query_params
        else ""
    )
    statuses = ", ".join(str(code) for code in item.statuses) or "n/d"
    return (
        f'<article class="group {sev}"><h4>{h.text(item.title, 160)}'
        f'<span class="badge {sev}">{SEVERITY_LABEL[sev]}</span></h4>'
        '<p class="muted">Técnica: leitura de resposta pela cerca '
        f"(<code>{h.plain(item.technique)}</code>); não é achado do ZAP. Achado "
        f"{h.ident(item.finding_id)}; CWE-{item.cwe}, {h.text(item.owasp_api_2023, 120)}; "
        f"confiança proposta {h.plain(item.proposed_confidence)}.</p>"
        f"<p><b>Onde:</b> {where}.</p>"
        f"<p><b>Respostas com o sinal:</b> {item.occurrences}, status {h.plain(statuses)}.</p>"
        f"{params}<p><b>O que significa:</b> {h.text(item.description, 600)}</p>"
        "<p><b>Direção de correção (sugestão genérica, não verificada):</b> "
        f"{h.text(item.solution, 400)}</p></article>"
    )


def signal_section(signals: ProxySignals | None) -> str:
    """Seção do `report.html`; vazia em relatório anterior ao ADR 0049 (`None`)."""
    if signals is None:
        return ""
    head = "<h2>Sinais vistos pela cerca</h2>"
    if not signals.enabled:
        return (
            f"{head}<p>Sem leitura: {h.text(signals.message or '', 300)}. Ausência de leitura "
            "não prova ausência de erros.</p>"
        )
    skipped = skipped_text(signals)
    rows = "".join(
        f"<li>{h.plain(RULE_BY_CATEGORY[key].label)} (<code>{h.plain(key)}</code>): "
        f"{count} resposta(s).</li>"
        for key, count in signals.counts.items()
        if key in RULE_BY_CATEGORY
    )
    omitted = (
        f'<p class="muted">{signals.findings_omitted} achado(s) de menor gravidade ficaram fora '
        "desta lista (error-signals.json); as contagens acima estão completas.</p>"
        if signals.findings_omitted
        else ""
    )
    return (
        f"{head}<p>Respostas liberadas lidas: {signals.responses_examined}; não lidas: "
        f"{sum(signals.responses_skipped.values())}"
        + (f" ({h.text(skipped, 500)})" if skipped else "")
        + f"; com algum sinal: {signals.responses_with_signal}.</p>"
        f'<p class="muted">{h.text(signals.notice, 900)}</p><ul>{rows}</ul>'
        + "".join(_finding(item) for item in signals.findings[:_MAX_ROWS])
        + omitted
    )
