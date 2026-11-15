"""Monta o pedido de um caso: o alvo e o corpo com UM campo alterado (ADR 0051).

Parte sempre do pedido que o `probe` provou (`exchanges.json`) e muda só o campo do caso; o
resto da consulta e do corpo fica como estava (um fator por vez). Este módulo é puro.
"""

import json
from urllib.parse import parse_qsl, quote, urlsplit

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.negative_plan import NegativeCase


def _text(value: JsonValue) -> str:
    """Texto do valor numa consulta (booleano e nulo não são gerados pelas classes)."""
    return value if isinstance(value, str) else json.dumps(value)


def _query_target(case: NegativeCase) -> str:
    parts = urlsplit(case.exchange.target)
    pairs: list[tuple[str, str]] = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        if name != case.field:
            pairs.append((name, value))
        elif not case.remove:
            pairs.append((name, _text(case.value)))
    query = "&".join(f"{quote(name, safe='')}={quote(value, safe='')}" for name, value in pairs)
    return f"{parts.path}?{query}" if query else parts.path


def render_case(case: NegativeCase) -> tuple[str, str | None]:
    """Alvo (caminho e consulta) e corpo JSON do pedido do caso.

    Returns:
        O alvo relativo à `base_url` e o corpo (texto JSON compacto), ou `None` sem corpo. O
        corpo original do `probe` vale quando o campo alterado é da consulta.
    """
    exchange = case.exchange
    if case.location == "query":
        return _query_target(case), exchange.body
    original = json.loads(exchange.body or "{}")
    body = dict(original)
    if case.remove:
        body.pop(case.field, None)
    else:
        body[case.field] = case.value
    return exchange.target, json.dumps(body, separators=(",", ":"), ensure_ascii=False)
