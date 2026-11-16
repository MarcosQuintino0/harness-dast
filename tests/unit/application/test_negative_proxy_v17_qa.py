"""Asserção de cerca distingue 429 operacional de recusa de escopo."""

from copy import deepcopy
from typing import Any

import pytest

from tests.integration.test_lab_negative import Round, unexpected_proxy_denials


def _row() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    common = {
        "method": "POST",
        "scheme": "http",
        "host": "clinica-piloto",
        "port": 8080,
        "path": "/api/auth/login",
    }
    proxy = {
        **common,
        "query_params": [],
        "decision": "deny",
        "reason": "rate_backoff",
        "status": 429,
        "ts": "2026-11-16T07:43:06.046+00:00",
    }
    cli = [
        {
            **common,
            "query_names": [],
            "seq": 77,
            "phase": "decision",
            "decision": "allowed",
            "timestamp": "2026-11-16T07:43:06.013122+00:00",
        },
        {
            **common,
            "query_names": [],
            "seq": 77,
            "phase": "result",
            "status": 429,
            "error": None,
            "timestamp": "2026-11-16T07:43:06.049865+00:00",
        },
    ]
    return proxy, cli


def _round(proxy: list[dict[str, Any]], cli: list[dict[str, Any]]) -> Round:
    return Round("write", 0, 0.0, {}, cli, proxy)


def test_429_de_backoff_com_trilha_correspondente_nao_e_recusa_de_escopo() -> None:
    proxy, cli = _row()
    assert unexpected_proxy_denials(_round([proxy], cli)) == []


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("reason", "deny_path"),
        ("status", 403),
        ("path", "/fora"),
        ("ts", "2026-11-16T07:44:00+00:00"),
        ("ts", "invalido"),
    ],
)
def test_recusa_distinta_ou_nao_correlacionada_continua_falhando(
    change: str, value: object
) -> None:
    proxy, cli = _row()
    proxy[change] = value
    assert unexpected_proxy_denials(_round([proxy], cli)) == [proxy]


def test_uma_tentativa_da_cli_nao_justifica_duas_recusas_do_proxy() -> None:
    proxy, cli = _row()
    duplicate = deepcopy(proxy)
    assert unexpected_proxy_denials(_round([proxy, duplicate], cli)) == [duplicate]


def test_sem_decisao_permitida_da_cli_o_429_nao_e_aceito() -> None:
    proxy, cli = _row()
    cli[0]["decision"] = "denied"
    assert unexpected_proxy_denials(_round([proxy], cli)) == [proxy]


def test_sem_429_da_cli_a_recusa_nao_e_aceita() -> None:
    proxy, cli = _row()
    cli[1]["status"] = 200
    assert unexpected_proxy_denials(_round([proxy], cli)) == [proxy]


def test_parametros_diferentes_nao_sao_a_mesma_tentativa() -> None:
    proxy, cli = _row()
    proxy["query_params"] = ["outro"]
    assert unexpected_proxy_denials(_round([proxy], cli)) == [proxy]


@pytest.mark.parametrize("decision", [None, "unknown", "not_sent"])
def test_estado_desconhecido_nao_e_aceito_como_recusa_operacional(decision: str | None) -> None:
    proxy, cli = _row()
    proxy["decision"] = decision
    assert unexpected_proxy_denials(_round([proxy], cli)) == [proxy]
