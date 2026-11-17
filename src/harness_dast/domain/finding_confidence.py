"""Degrau de confiança de um achado: três degraus, não nota (aba "Falhas" do painel).

- `a confirmar`: a ferramenta apontou, mas a resposta gravada não mostra a falha sozinha (ou o
  agente suspeita de falso positivo);
- `prova forte`: a resposta gravada mostra a falha. Regra fixa e ÚNICA do projeto (o painel a
  usa, e o ADR 0032 a descreve): há evidência guardada, o ZAP apontou um trecho dela como prova
  e nem o ZAP nem o agente a marcaram como falso positivo. A confiança que o ZAP propõe
  (`low`, `medium`, `high`) NÃO entra: um erro 500 depois de uma aspa costuma vir como `low` e a
  resposta gravada prova a falha; medido na Clínica Piloto (execução f087), 2 dos 3 achados
  graves são prova forte e 1 (falha por demora, sem trecho na resposta) fica a confirmar;
- `confirmada`: uma pessoa repetiu e registrou que viu. NUNCA sai do cálculo sozinho.

A confirmação humana é registrada em `human-confirmations.json` (ADR 0086), separada da
triagem. O leitor valida produto e execução e consulta `HumanConfirmations.contains(fingerprint)`;
então passa o resultado como `confirmed_by_person`. Sem registro, mantém o padrão False.

A função não altera o achado: severidade e confiança propostas pelo ZAP continuam as mesmas.
Este módulo é puro.
"""

from typing import Final, Literal

from harness_dast.domain.finding import Finding, TriageNote

ConfidenceStep = Literal["a confirmar", "prova forte", "confirmada"]
"""Lista fechada de `docs/design/execution-panel/system/formats.html`."""

_ZAP_FALSE_POSITIVE: Final = "false_positive"


def confidence_step(
    finding: Finding,
    triage: TriageNote | None = None,
    *,
    confirmed_by_person: bool = False,
) -> ConfidenceStep:
    """Degrau de confiança do achado.

    Args:
        finding: O achado (com a evidência da melhor ocorrência).
        triage: Anotação de triagem; sem ela, vale a que já veio mesclada em `finding.triage`.
        confirmed_by_person: `True` só quando uma pessoa registrou que repetiu e viu a falha.
            Obtenha o valor do envelope validado da mesma execução, por fingerprint.

    Returns:
        `confirmada` se uma pessoa confirmou; `a confirmar` se o agente ou o ZAP indicam falso
        positivo ou se não há prova na resposta gravada; `prova forte` nos demais casos.
    """
    if confirmed_by_person:
        return "confirmada"
    note = triage if triage is not None else finding.triage
    if note is not None and note.suspected_false_positive:
        return "a confirmar"
    evidence = finding.evidence
    has_proof = evidence.available and bool(evidence.zap_evidence.strip())
    if has_proof and finding.proposed_confidence != _ZAP_FALSE_POSITIVE:
        return "prova forte"
    return "a confirmar"
