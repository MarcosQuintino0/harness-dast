"""QA independente: um OpenAPI NÃO CONFIÁVEL não pode controlar cabeçalhos de roteamento.

O documento OpenAPI é entrada de terceiros (o próprio loader o trata assim). Um parâmetro
`in: header` chamado `Host` faz a requisição sair com `Host: <valor da regra>` para a URL
permitida: um proxy reverso ou balanceador roteia pelo cabeçalho, e a requisição alcança outro
virtual host. `approve()` só confere método e URL, e o perfil já proíbe esses nomes nos
cabeçalhos de autenticação (`auth._RESERVED_HEADERS`), mas o montador de requisição não aplica a
mesma lista aos parâmetros do OpenAPI.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.request_builder import RequestBuilder
from harness_dast.domain.request_encoding import encode_built_request

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
ROUTING_HEADERS = [
    "Host",
    "host",
    "Content-Length",
    "Transfer-Encoding",
    "Connection",
    "Upgrade",
    "TE",
    "Expect",
    "Proxy-Authorization",
    "Proxy-Connection",
]


def encoded_headers(tmp_path: Path, header_name: str) -> dict[str, str]:
    spec_doc = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/a": {
                "get": {
                    "operationId": "a",
                    "parameters": [
                        {
                            "name": header_name,
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    path = tmp_path / "api.json"
    path.write_text(json.dumps(spec_doc), encoding="utf-8")
    spec = load_spec(path)
    rules = DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [
                {
                    "match": {"field": header_name},
                    "generator": "constant",
                    "args": {"value": "outro-host.interno.example"},
                }
            ],
        }
    )
    built = RequestBuilder(rules, GeneratorCatalogue(1, NOW), "7f3a").build(spec.operations[0])
    request = encode_built_request(built, base_url="https://api.exemplo.com", account=None)
    return {name.lower(): value for name, value in request.headers}


@pytest.mark.parametrize("header_name", ROUTING_HEADERS)
def test_encode_built_request_never_sends_a_routing_header_declared_by_the_openapi(
    tmp_path: Path, header_name: str
) -> None:
    headers = encoded_headers(tmp_path, header_name)

    assert header_name.lower() not in headers
