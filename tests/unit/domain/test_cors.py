"""Contrato das políticas CORS observáveis pelo navegador."""

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz.config import AuthzConfig
from harness_dast.domain.cors import classify_cors, cors_finding
from harness_dast.domain.probe_exchange import ExchangeRecord

ORIGIN = "https://test.invalid"


@pytest.mark.parametrize(
    ("allowed", "credentials", "expected"),
    [
        (ORIGIN, "true", "reflected_credentials"),
        ("*", None, "wildcard"),
        ("*", "false", "wildcard"),
        ("*", "true", None),
        (ORIGIN, None, None),
        (ORIGIN, "True", None),
        ("https://other.invalid", "true", None),
        (f"{ORIGIN}, {ORIGIN}", "true", None),
        (None, None, None),
    ],
)
def test_classifica_resposta_pela_politica_do_navegador(
    allowed: str | None, credentials: str | None, expected: str | None
) -> None:
    assert classify_cors(ORIGIN, allowed, credentials) == expected


def test_fingerprint_identifica_politica_e_nao_operacao() -> None:
    first = ExchangeRecord(
        operation_id="a", method="GET", path="/a", target="/a", account="a", status=200
    )
    second = first.model_copy(update={"operation_id": "b", "path": "/b", "target": "/b"})
    a = cors_finding("product", first, None, 200, "reflected_credentials")
    b = cors_finding("product", second, None, 200, "reflected_credentials")
    assert a.fingerprint == b.fingerprint
    assert (a.proposed_severity, a.cwe) == ("high", 942)
    assert cors_finding("product", first, None, 200, "wildcard").proposed_severity == "low"


@pytest.mark.parametrize("value", [-1, 11, True, "2", None])
def test_limite_rejeita_valor_invalido(value: object) -> None:
    with pytest.raises(ValidationError):
        AuthzConfig.model_validate({"cors_max_requests": value})
