"""Contrato da auditoria de sinais usado na checagem de ausência de texto bruto."""

import pytest

from tests.integration.test_lab_error_signals import assert_audit_row_has_no_response_text


@pytest.mark.parametrize(
    "row", [{}, {"grant_wait_ms": 0}, {"network_ms": 1}, {"grant_wait_ms": 2, "network_ms": 3}]
)
def test_auditoria_aceita_tempos_opcionais_inteiros_nao_negativos(row: dict[str, object]) -> None:
    assert_audit_row_has_no_response_text(row)


@pytest.mark.parametrize("field", ["grant_wait_ms", "network_ms"])
@pytest.mark.parametrize("value", [-1, 1.5, "1", "", True, None])
def test_auditoria_rejeita_tempo_invalido(field: str, value: object) -> None:
    with pytest.raises(AssertionError, match=field):
        assert_audit_row_has_no_response_text({field: value})


def test_auditoria_rejeita_campo_de_texto_extra() -> None:
    with pytest.raises(AssertionError):
        assert_audit_row_has_no_response_text({"response_text": "trecho sintético"})
