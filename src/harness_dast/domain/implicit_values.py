"""Escolha do gerador implícito de um campo que nenhuma regra cobre.

Dado o esquema (tipo, formato, limites, `pattern`), decide qual gerador do catálogo e quais
argumentos produzem um valor válido, sem aleatoriedade neste módulo. Quando o harness não
sabe gerar sozinho (por exemplo, um `pattern` complexo), levanta `FieldNotGeneratable` com a
instrução de escrever uma regra, em vez de chutar. Este módulo é puro.
"""

import math

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.datagen_catalog import MAX_ARG_TEXT
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.pattern_subset import parse_pattern, synthesize

_STRING_FORMATS = {
    "uuid": "uuid",
    "email": "email",
    "uri": "uri",
    "url": "uri",
    "date": "date",
    "date-time": "datetime",
}
_FIXED_FORMATS = {"ipv4": "192.0.2.10", "hostname": "host.example.test"}
_INT_RANGES = {"int32": (-(2**31), 2**31 - 1), "int64": (-(2**63), 2**63 - 1)}
_DEFAULT_TEXT_LENGTH = 10
_MAX_TEXT_LENGTH = 256
_DEFAULT_SPAN = 100_000
_RULE_HINT = "Escreva uma regra em data-rules.yml para este campo."

type Draw = tuple[str, dict[str, JsonValue]]


class FieldNotGeneratable(ConfigError):
    """Campo para o qual o harness não sabe gerar um valor válido sozinho."""


def implicit_draw(flat: Schema, schema_type: str | None, display: str) -> Draw:
    """Escolhe o gerador e os argumentos para um campo sem regra.

    Args:
        flat: Esquema do campo, já sem composição.
        schema_type: Tipo efetivo (`None` = não declarado; tratado como texto).
        display: Caminho legível do campo, só para mensagens.

    Returns:
        Par (nome do gerador, argumentos).

    Raises:
        FieldNotGeneratable: Limites impossíveis ou `pattern` fora do subconjunto seguro.
    """
    if schema_type == "boolean":
        return "boolean", {}
    if schema_type in {"integer", "number"}:
        low, high = numeric_bounds(flat, display)
        if schema_type == "integer":
            return "integer", {"min": low, "max": high}
        return "number", {"min": low, "max": high}
    return _string_draw(flat, display)


def numeric_bounds(flat: Schema, display: str) -> tuple[int, int]:
    """Intervalo inteiro [min, max] que o esquema admite (com padrões amplos se aberto).

    Raises:
        FieldNotGeneratable: Se os limites não admitem nenhum inteiro.
    """
    low = _lower(flat)
    high = _upper(flat)
    floor, ceiling = _INT_RANGES.get(flat.format or "", _INT_RANGES["int64"])
    if low is None:
        low = 1 if high is None or high >= 1 else max(high - 1000, floor)
    if high is None:
        high = min(low + _DEFAULT_SPAN, ceiling)
    low, high = max(low, floor), min(high, ceiling)
    if low > high:
        raise FieldNotGeneratable(
            f"Os limites de {safe_identifier(display)} não admitem nenhum valor inteiro.",
            hint=_RULE_HINT,
        )
    return low, high


def _lower(flat: Schema) -> int | None:
    if flat.minimum is None:
        return None
    bound = math.ceil(flat.minimum)
    return bound + 1 if flat.exclusive_minimum and bound == flat.minimum else bound


def _upper(flat: Schema) -> int | None:
    if flat.maximum is None:
        return None
    bound = math.floor(flat.maximum)
    return bound - 1 if flat.exclusive_maximum and bound == flat.maximum else bound


def _string_draw(flat: Schema, display: str) -> Draw:
    if flat.pattern is not None:
        return _pattern_draw(flat.pattern, flat, display)
    if flat.format in _STRING_FORMATS:
        return _STRING_FORMATS[flat.format], {}
    if flat.format in _FIXED_FORMATS:
        return "constant", {"value": _FIXED_FORMATS[flat.format]}
    low = flat.min_length or 0
    if flat.max_length == 0:
        return "constant", {"value": ""}
    if low > _MAX_TEXT_LENGTH:
        raise FieldNotGeneratable(
            f"{safe_identifier(display)} exige texto maior que {_MAX_TEXT_LENGTH} caracteres.",
            hint=_RULE_HINT,
        )
    length = max(_DEFAULT_TEXT_LENGTH, low, 1)
    if flat.max_length is not None:
        length = min(length, flat.max_length)
    return "alphanumeric", {"length": length}


def _pattern_draw(pattern: str, flat: Schema, display: str) -> Draw:
    parsed = parse_pattern(pattern)
    if parsed is None:
        raise FieldNotGeneratable(
            f"O pattern de {safe_identifier(display)} é complexo demais para gerar um valor "
            "sozinho.",
            hint=_RULE_HINT,
        )
    text = synthesize(parsed, flat.min_length or 0, flat.max_length)
    if text is None or len(text) > MAX_ARG_TEXT:
        raise FieldNotGeneratable(
            f"Não há valor que atenda ao pattern e aos tamanhos de {safe_identifier(display)}.",
            hint=_RULE_HINT,
        )
    return "constant", {"value": text}
