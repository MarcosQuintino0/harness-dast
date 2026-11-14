from harness_dast.domain.finding import (
    Classification,
    Finding,
    FindingEvidence,
    TriageNote,
)
from harness_dast.domain.finding_confidence import confidence_step
from harness_dast.domain.zap_alert import Confidence


def _finding(
    *,
    zap_evidence: str = "trecho",
    available: bool = True,
    confidence: Confidence = "high",
    triage: TriageNote | None = None,
) -> Finding:
    return Finding(
        finding_id="F-00000001",
        fingerprint="a" * 64,
        title="SQL Injection",
        plugin_id="40018",
        alert_ref="40018",
        classification=Classification(cwe=89),
        proposed_severity="high",
        proposed_confidence=confidence,
        method="GET",
        path_template="/x",
        attribution="source_message",
        occurrences=1,
        evidence=FindingEvidence(zap_evidence=zap_evidence, available=available),
        triage=triage,
    )


def test_confidence_step_e_prova_forte_com_evidencia_e_trecho_de_prova() -> None:
    assert confidence_step(_finding()) == "prova forte"


def test_confidence_step_aceita_confianca_confirmada_do_zap_como_prova_forte() -> None:
    assert confidence_step(_finding(confidence="confirmed")) == "prova forte"


def test_confidence_step_e_a_confirmar_sem_trecho_de_prova() -> None:
    assert confidence_step(_finding(zap_evidence="  ")) == "a confirmar"


def test_confidence_step_e_a_confirmar_sem_evidencia_guardada() -> None:
    assert confidence_step(_finding(available=False)) == "a confirmar"


def test_confidence_step_nao_depende_da_confianca_que_o_zap_propoe() -> None:
    # Erro 500 depois de uma aspa costuma vir "low", e a resposta gravada prova a falha.
    assert confidence_step(_finding(confidence="low")) == "prova forte"
    assert confidence_step(_finding(confidence="medium")) == "prova forte"


def test_confidence_step_e_a_confirmar_quando_o_zap_marca_falso_positivo() -> None:
    assert confidence_step(_finding(confidence="false_positive")) == "a confirmar"


def test_confidence_step_e_a_confirmar_quando_o_agente_suspeita_de_falso_positivo() -> None:
    note = TriageNote(suspected_false_positive=True, reason="parece esperado")

    assert confidence_step(_finding(triage=note)) == "a confirmar"


def test_confidence_step_usa_a_anotacao_passada_em_vez_da_mesclada() -> None:
    merged = TriageNote(suspected_false_positive=True, reason="x")

    assert confidence_step(_finding(triage=merged), TriageNote()) == "prova forte"


def test_confidence_step_nunca_chega_a_confirmada_so_pela_triagem_do_agente() -> None:
    note = TriageNote(note="confirmei", suspected_false_positive=False)

    assert confidence_step(_finding(confidence="confirmed", triage=note)) != "confirmada"


def test_confidence_step_so_e_confirmada_quando_uma_pessoa_confirmou() -> None:
    assert confidence_step(_finding(), confirmed_by_person=True) == "confirmada"


def test_confidence_step_nao_altera_o_achado() -> None:
    finding = _finding()
    before = finding.model_dump()

    confidence_step(finding)

    assert finding.model_dump() == before
