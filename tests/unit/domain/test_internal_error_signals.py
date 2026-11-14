"""Testa sinais passivos em evidências redigidas."""

from harness_dast.domain.internal_error_signals import classify_internal_error_signals
from harness_dast.domain.redaction import EvidenceMessage


def test_classifica_respostas_e_deduplica_mensagem() -> None:
    evidence = {
        1: EvidenceMessage(
            message_id=7,
            response_header="HTTP/1.1 500 Internal Server Error",
            response_body="ORA-12345 senha privada",
        ),
        2: EvidenceMessage(
            message_id=7, response_body="Traceback (most recent call last)", truncated=True
        ),
        3: EvidenceMessage(
            message_id=8, response_header="HTTP/2 503", response_body="SQLSTATE[23505]"
        ),
    }
    result = classify_internal_error_signals(evidence)
    assert result.messages_examined == 2
    assert result.truncated_messages == 1
    assert result.counts == {"http_5xx": 2, "stack_trace": 1, "sql_error": 2}
    assert "senha privada" not in result.model_dump_json()


def test_ignora_requisicao_e_textos_genericos() -> None:
    result = classify_internal_error_signals(
        {
            1: EvidenceMessage(
                message_id=1, request_body="ORA-12345", response_body="server error and exception"
            )
        }
    )
    assert result.counts == {"http_5xx": 0, "stack_trace": 0, "sql_error": 0}


def test_entrada_vazia_tem_contagens_zero() -> None:
    result = classify_internal_error_signals({})
    assert result.messages_examined == 0
    assert all(count == 0 for count in result.counts.values())


def test_resultado_independe_da_ordem() -> None:
    a = EvidenceMessage(message_id=1, response_body="ORA-12345")
    b = EvidenceMessage(message_id=1, response_header="HTTP/1.1 500 error")
    assert classify_internal_error_signals({1: a, 2: b}) == classify_internal_error_signals(
        {2: b, 1: a}
    )


def test_frame_java_e_falsos_inicios_em_linha_longa() -> None:
    body = "at Nome(" * 400 + " at pacote.Classe.metodo(Classe.java:42)"
    result = classify_internal_error_signals({1: EvidenceMessage(message_id=1, response_body=body)})
    assert result.counts["stack_trace"] == 1
    only_false = classify_internal_error_signals(
        {1: EvidenceMessage(message_id=1, response_body="at Nome(" * 400)}
    )
    assert only_false.counts["stack_trace"] == 0
