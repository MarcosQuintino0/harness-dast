"""Dados de perfil para os testes: um perfil válido, sem valores de exemplo do modelo."""

import copy
from typing import Any

import yaml

from harness_dast.domain.profile import ProductProfile

# Autorização longa e janela de 24 h todos os dias: o perfil fica executável em qualquer
# instante em que o teste rode, sem depender do relógio.
ALWAYS_OPEN_WINDOW = "seg-dom 00:00-24:00 UTC"


def valid_profile_data(product: str = "demo", *, with_cleanup: bool = False) -> dict[str, Any]:
    """Devolve um dicionário de perfil estruturalmente válido e sem placeholders."""
    data: dict[str, Any] = {
        "schema_version": 1,
        "product": product,
        "environment": {"name": "homolog", "base_url": "https://api.hml.acme-teste.net.br"},
        "openapi": "./openapi.json",
        "scope": {
            "allow": [
                {
                    "host": "api.hml.acme-teste.net.br",
                    "paths": ["/api/**"],
                    "methods": ["GET", "POST"],
                }
            ],
            "deny_paths": ["/api/admin/**"],
            "authorization": {"reference": "CHG-4821", "valid_until": "2999-12-31"},
            "windows": [ALWAYS_OPEN_WINDOW],
        },
        "limits": {"requests_per_second": 5, "max_duration_minutes": 60, "zap_threads_per_host": 2},
        "auth": {
            "type": "login_password",
            "token_path": "/api/auth/login",
            "request_encoding": "json",
            "accounts": [
                {
                    "alias": "user_a",
                    "role": "usuario",
                    "username": {"secret_ref": "env:ACME_USER_A_LOGIN"},
                    "password": {"secret_ref": "env:ACME_USER_A_SENHA"},
                }
            ],
        },
    }
    if with_cleanup:
        data["cleanup"] = {
            "type": "oracle_sql",
            "script": "./cleanup/cleanup.sql",
            "connection": {"secret_ref": "env:ACME_ORACLE_LIMPEZA"},
            "requires_confirmation": True,
        }
    return copy.deepcopy(data)


def valid_profile(product: str = "demo", *, with_cleanup: bool = False) -> ProductProfile:
    """Devolve o perfil válido já validado pelo domínio."""
    return ProductProfile.from_data(valid_profile_data(product, with_cleanup=with_cleanup))


def dump_yaml(data: dict[str, Any]) -> str:
    """Serializa o dicionário como o YAML que uma pessoa escreveria (sem reordenar chaves)."""
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
