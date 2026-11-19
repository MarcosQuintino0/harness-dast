"""Nuclei no painel (ADR 0122): só o mínimo para mostrar a contagem e a seção. Módulo puro.

O painel está congelado (ADR 0110); este módulo reúne o que o Nuclei precisa para aparecer sem
tocar no resto: a falha grave do Nuclei, o resumo (contagens) e o cartão da aba Falhas. Os dados
vêm do `findings.json` (`report.nuclei`), já sem requisição, resposta, `curl-command` nem valor
extraído. Texto que veio do alvo sai por `html_safe`; nunca diz "seguro" nem "aprovado".
"""

from harness_dast.domain import html_safe as h
from harness_dast.domain.nuclei_findings import NucleiFinding
from harness_dast.domain.panel.format import plural
from harness_dast.domain.panel.model import PanelFinding, PanelNuclei
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.report.nuclei import extracted_text, where_text

_WEAK = 1
_DESCRIPTION = (
    "Modelo conhecido do catálogo do Nuclei, que casou na resposta do sistema de teste. A "
    "gravidade é proposta pelo código e todo achado pede triagem."
)


def nuclei_severe(report: FindingsReport | None) -> tuple[PanelFinding, ...]:
    """Falhas graves (severidade proposta `high`) do Nuclei, com a prova mais fraca (a triar)."""
    if report is None or report.nuclei is None:
        return ()
    return tuple(
        _finding(item) for item in report.nuclei.findings if item.proposed_severity == "high"
    )


def _finding(item: NucleiFinding) -> PanelFinding:
    record = item.record
    note = item.triage
    return PanelFinding(
        finding_id=item.finding_id,
        fingerprint=item.fingerprint,
        origin="nuclei",
        title=record.template_id,
        severity=item.proposed_severity,
        confidence=_WEAK,
        method=record.method or "-",
        path_template=record.matched_path,
        occurrences=item.occurrences,
        description=_DESCRIPTION,
        nuclei_evidence=(
            f"Modelo {record.template_id} ({record.template_path}) em "
            f"{where_text(record.method, record.matched_path)}; {item.occurrences} "
            f"ocorrência(s); {extracted_text(item)}."
        ),
        suspected_false_positive=None if note is None else note.suspected_false_positive,
        triage_note=(note.note or None) if note else None,
    )


def build_nuclei_summary(report: FindingsReport | None) -> PanelNuclei | None:
    """Contagens do estágio, ou `None` quando o Nuclei não rodou."""
    if report is None or report.nuclei is None:
        return None
    nuclei = report.nuclei
    return PanelNuclei(
        status=nuclei.status,
        findings=len(nuclei.findings),
        severe=sum(1 for item in nuclei.findings if item.proposed_severity == "high"),
        technologies=len(nuclei.technologies),
    )


def render_nuclei_card(nuclei: PanelNuclei | None) -> str:
    """Bloco da lista da aba Falhas com a contagem do Nuclei; vazio sem o estágio."""
    if nuclei is None:
        return ""
    found = plural(nuclei.findings, "achado", "achados")
    technologies = plural(
        nuclei.technologies, "tecnologia identificada", "tecnologias identificadas"
    )
    stopped = (
        ""
        if nuclei.status == "completed"
        else " O Nuclei parou antes do fim: o que ele não rodou não deve ser lido como livre de "
        "exposição conhecida."
    )
    return (
        f'<h2 class="h" style="margin-top: 10px">Nuclei · {nuclei.findings}</h2>'
        '<p class="sm mu">Segundo motor, só modelos conhecidos de exposição: '
        f"{h.plain(found)} ({nuclei.severe} grave(s)) e {h.plain(technologies)} (tecnologia não "
        "é achado). Os detalhes estão na seção Nuclei do relatório completo."
        f"{h.plain(stopped)}</p>"
    )
