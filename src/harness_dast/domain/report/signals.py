"""Seção "Sinais vistos pela cerca" do `report.md` (ADR 0049). Módulo puro.

Mostra quantas respostas liberadas a cerca leu, quantas ficaram sem leitura e por quê, quantas
traziam cada sinal e os achados de origem própria (`proxy`). Nada aqui veio do corpo de uma
resposta: só categoria, método, modelo de caminho, códigos HTTP e nomes de parâmetro, que passam
pelo mesmo escape do resto do relatório. Zero sinal vem sempre com a base de respostas lidas.
"""

from typing import Final

from harness_dast.domain.error_signal_catalog import RULE_BY_CATEGORY
from harness_dast.domain.markdown_safe import code_span, escape_inline
from harness_dast.domain.report.labels import SEVERITY_LABEL
from harness_dast.domain.signal_result import ProxySignals, SignalFinding

PASSIVE_SUBSET_NOTE: Final = (
    "Esta contagem é um subconjunto das respostas (só as evidências que o ZAP guardou); a "
    "contagem completa está em 'Sinais vistos pela cerca'."
)
SKIP_LABEL: Final = {
    "type": "tipo de conteúdo que não é texto de erro (imagem, script, estilo, binário)",
    "encoding": "codificação que a cerca não abre (por exemplo br ou zstd) ou dado corrompido",
    "empty": "sem corpo",
    "error": "falha inesperada da leitura (a resposta passou do mesmo jeito)",
}


def has_signal_reading(signals: ProxySignals | None) -> bool:
    """Se a cerca leu esta execução (base para a nota do ADR 0045 e para o resumo)."""
    return signals is not None and signals.enabled


def skipped_text(signals: ProxySignals) -> str:
    """Respostas sem leitura, por motivo, em português (vazio quando não houve)."""
    return "; ".join(
        f"{count} por {SKIP_LABEL.get(reason, reason)}"
        for reason, count in signals.responses_skipped.items()
        if count
    )


def _finding_lines(item: SignalFinding) -> list[str]:
    where = code_span(f"{item.method} {item.path_template}")
    if item.operation_id:
        where += f", operação {code_span(item.operation_id)}"
    statuses = ", ".join(str(code) for code in item.statuses) or "n/d"
    lines = [
        f"### {code_span(item.finding_id)} {escape_inline(item.title, 160)}",
        "",
        "- **Técnica:** leitura de resposta pela cerca (`proxy_error_signal`), não do ZAP.",
        f"- **Severidade proposta pelo código:** {SEVERITY_LABEL[item.proposed_severity]}; "
        f"confiança proposta: {escape_inline(item.proposed_confidence)}. Status: needs_triage.",
        f"- **Onde:** {where}.",
        f"- **Classe:** CWE-{item.cwe}, {escape_inline(item.owasp_api_2023)}.",
        f"- **Respostas com o sinal:** {item.occurrences}, status {statuses}.",
    ]
    if item.query_params:
        names = ", ".join(code_span(name, 80) for name in item.query_params)
        lines.append(f"- **Parâmetros de consulta (só nomes):** {names}.")
    lines += [
        f"- **Fingerprint:** {code_span(item.fingerprint)}.",
        "",
        f"**O que significa:** {escape_inline(item.description, 600)}",
        f"**Direção de correção (sugestão genérica):** {escape_inline(item.solution, 400)}",
    ]
    return lines


def signal_summary_lines(by_severity: dict[str, int]) -> list[str]:
    """Tabela de achados de sinal por severidade (vazia quando a cerca não leu)."""
    if not by_severity:
        return []
    lines = ["", "Sinais de erro interno vistos pela cerca (técnica própria, não é do ZAP):", ""]
    lines += ["| Severidade proposta pelo código | Achados |", "|---|---|"]
    lines += [f"| {SEVERITY_LABEL[name]} | {count} |" for name, count in by_severity.items()]
    return lines


def signal_lines(signals: ProxySignals | None) -> list[str]:
    """Seção completa; vazia em relatório anterior ao ADR 0049 (`None`)."""
    if signals is None:
        return []
    head = ["## Sinais vistos pela cerca", ""]
    if not signals.enabled:
        return [
            *head,
            f"Sem leitura: {escape_inline(signals.message or '', 300)}. Ausência de leitura não "
            "prova ausência de erros.",
        ]
    skipped = skipped_text(signals)
    lines = [
        *head,
        f"Respostas liberadas lidas: {signals.responses_examined}; não lidas: "
        f"{sum(signals.responses_skipped.values())}"
        + (f" ({escape_inline(skipped, 500)})" if skipped else "")
        + f"; com algum sinal: {signals.responses_with_signal}.",
        "",
        escape_inline(signals.notice, 900),
        "",
    ]
    lines += [
        f"- {escape_inline(RULE_BY_CATEGORY[key].label)} ({code_span(key, 40)}): "
        f"{count} resposta(s)."
        for key, count in signals.counts.items()
        if key in RULE_BY_CATEGORY
    ]
    for item in signals.findings:
        lines += ["", *_finding_lines(item)]
    if signals.findings_omitted:
        lines += [
            "",
            f"{signals.findings_omitted} achado(s) de menor gravidade ficaram fora desta lista "
            "(error-signals.json); as contagens acima estão completas.",
        ]
    return lines
