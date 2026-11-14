"""Dados de carta estruturada para os testes: uma carta válida do laboratório, sem valor-modelo."""

import copy
from typing import Any


def answer(value: object, source: str = "carta", quote: str | None = None) -> dict[str, Any]:
    """Uma resposta do formulário (`{value, source, quote?}`)."""
    result: dict[str, Any] = {"value": value, "source": source}
    if quote is not None:
        result["quote"] = quote
    return result


def valid_letter_data(product: str = "demo") -> dict[str, Any]:
    """Carta estruturada válida: login por senha, duas contas do mesmo papel."""
    return copy.deepcopy(
        {
            "schema_version": 1,
            "product": product,
            "gates": {
                "test_environment": answer(True),
                "synthetic_data": answer(True),
                "authorization_in_force": answer(True, "pessoa"),
                "product_owner": answer("Dona do Produto (dona@acme-teste.net.br)"),
            },
            "environment": {
                "name": answer("homolog"),
                "base_url": answer("https://api.hml.acme-teste.net.br"),
                "openapi": answer("./openapi.json", "pessoa"),
            },
            "scope": {
                "allow": answer(
                    [
                        {
                            "host": "api.hml.acme-teste.net.br",
                            "paths": ["/api/**"],
                            "methods": ["GET", "POST"],
                        }
                    ]
                ),
                "deny_paths": answer(["/api/admin/**"]),
            },
            "authorization": {
                "reference": answer("CHG-4821"),
                "valid_until": answer("2999-12-31"),
                "windows": answer(["seg-dom 00:00-24:00 UTC"]),
            },
            "limits": {
                "requests_per_second": answer(5),
                "max_duration_minutes": answer(60),
                "zap_threads_per_host": answer(2),
            },
            "auth": {
                "type": answer("login_password", "pessoa"),
                "token_path": answer("/api/auth/login", "pessoa"),
                "accounts": answer(
                    [
                        {
                            "alias": "user_a",
                            "role": "usuario",
                            "username": {"secret_ref": "env:ACME_USER_A_LOGIN"},
                            "password": {"secret_ref": "env:ACME_USER_A_SENHA"},
                        }
                    ]
                ),
            },
        }
    )
