"""Conferência de um valor escalar contra o esquema, sem repetir o valor nas mensagens.

Usada pelo montador de requisições para garantir que o que um gerador devolveu cabe no
campo (tipo, enum, limites, tamanho, formato e, quando suportado, `pattern`). Este módulo é
puro.
"""

import re
from datetime import date, datetime
from typing import TypeGuard
from urllib.parse import urlsplit

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.pattern_subset import matches, parse_pattern

_INT_RANGES = {"int32": (-(2**31), 2**31 - 1), "int64": (-(2**63), 2**63 - 1)}
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _is_number(value: JsonValue) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _type_matches(schema_type: str, value: JsonValue) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return _is_number(value)
    if schema_type == "boolean":
        return isinstance(value, bool)
    return value is None if schema_type == "null" else False


def _same(left: JsonValue, right: JsonValue) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def _check_number(schema: Schema, value: float) -> list[str]:
    problems: list[str] = []
    low, high = schema.minimum, schema.maximum
    if low is not None and (value < low or (schema.exclusive_minimum and value == low)):
        problems.append("abaixo do mínimo")
    if high is not None and (value > high or (schema.exclusive_maximum and value == high)):
        problems.append("acima do máximo")
    bounds = _INT_RANGES.get(schema.format or "")
    if bounds is not None and not bounds[0] <= value <= bounds[1]:
        problems.append(f"fora do intervalo de {schema.format}")
    return problems


def _check_format(schema_format: str, value: str) -> bool:
    if schema_format == "date":
        return _DATE.fullmatch(value) is not None and _valid_date(value)
    if schema_format == "date-time":
        return "T" in value and _has_zone(value)
    if schema_format == "uuid":
        return _UUID.fullmatch(value) is not None
    if schema_format == "email":
        return _EMAIL.fullmatch(value) is not None
    if schema_format in {"uri", "url"}:
        parts = urlsplit(value)
        return bool(parts.scheme and parts.netloc) and " " not in value
    return True


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _has_zone(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _check_text(schema: Schema, value: str) -> list[str]:
    problems: list[str] = []
    if schema.min_length is not None and len(value) < schema.min_length:
        problems.append("menor que min_length")
    if schema.max_length is not None and len(value) > schema.max_length:
        problems.append("maior que max_length")
    if schema.format is not None and not _check_format(schema.format, value):
        problems.append(f"fora do formato {schema.format}")
    parsed = parse_pattern(schema.pattern) if schema.pattern is not None else None
    if parsed is not None and not matches(parsed, value):
        problems.append("não casa com o pattern")
    return problems


def violations(schema: Schema, value: JsonValue) -> tuple[str, ...]:
    """Lista, em português, o que no `value` contraria o esquema (vazio = válido).

    As mensagens nunca contêm o valor. `pattern` só é conferido quando está no subconjunto
    seguro de `pattern_subset`; um padrão fora dele é aceito sem conferência. O esquema deve
    estar achatado (sem composição) e ser de um valor escalar.

    Args:
        schema: Esquema do campo.
        value: Valor candidato.

    Returns:
        Tupla de problemas encontrados.
    """
    if value is None:
        return () if schema.nullable or schema.type in {None, "null"} else ("nulo não permitido",)
    if schema.type is not None and not _type_matches(schema.type, value):
        return (f"tipo diferente de {schema.type}",)
    problems: list[str] = []
    if schema.enum is not None and not any(_same(value, option) for option in schema.enum):
        problems.append("fora do enum")
    if _is_number(value):
        problems.extend(_check_number(schema, value))
    if isinstance(value, str):
        problems.extend(_check_text(schema, value))
    return tuple(problems)
