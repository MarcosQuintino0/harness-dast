"""Oráculo independente para os testes: diz se um valor JSON satisfaz um `Schema`.

Escrito sem reutilizar `schema_check` do domínio, de propósito: se os dois divergirem, um
teste de propriedade falha. Aqui vale a regra de JSON Schema "ao pé da letra".
"""

import re
from datetime import datetime

from harness_dast.domain.api_schema import JsonValue, Schema

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_int(value: JsonValue) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_num(value: JsonValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _format_ok(fmt: str | None, value: str) -> bool:
    if fmt == "uuid":
        return bool(_UUID.match(value))
    if fmt == "email":
        return bool(_EMAIL.match(value))
    if fmt == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
        return bool(_DATE.match(value))
    if fmt == "date-time":
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return False
        return True
    if fmt in {"uri", "url"}:
        return bool(re.match(r"^[a-z][a-z0-9+.-]*://[^\s/]+(/\S*)?$", value))
    return True


def _scalar_ok(schema: Schema, value: JsonValue) -> bool:
    if schema.enum is not None and not any(
        type(value) is type(option) and value == option for option in schema.enum
    ):
        return False
    if schema.type == "string":
        return isinstance(value, str) and _string_ok(schema, value)
    if schema.type == "integer":
        return _is_int(value) and _number_ok(schema, value)
    if schema.type == "number":
        return _is_num(value) and _number_ok(schema, value)
    if schema.type == "boolean":
        return isinstance(value, bool)
    return True


def _string_ok(schema: Schema, value: str) -> bool:
    if schema.min_length is not None and len(value) < schema.min_length:
        return False
    if schema.max_length is not None and len(value) > schema.max_length:
        return False
    if schema.pattern is not None and re.search(schema.pattern, value) is None:
        return False
    return _format_ok(schema.format, value)


def _number_ok(schema: Schema, value: JsonValue) -> bool:
    if not isinstance(value, int | float):
        return False
    low, high = schema.minimum, schema.maximum
    if low is not None and (value < low or (schema.exclusive_minimum and value == low)):
        return False
    if high is not None and (value > high or (schema.exclusive_maximum and value == high)):
        return False
    if schema.format == "int32":
        return -(2**31) <= value < 2**31
    return True


def conforms(schema: Schema, value: JsonValue) -> bool:
    """Verdadeiro se `value` satisfaz `schema` (incluindo composição e aninhamento)."""
    if value is None:
        return schema.nullable or schema.type in {None, "null"}
    if not all(conforms(part, value) for part in schema.all_of):
        return False
    if schema.one_of and not any(conforms(part, value) for part in schema.one_of):
        return False
    if schema.any_of and not any(conforms(part, value) for part in schema.any_of):
        return False
    if isinstance(value, dict):
        return _object_ok(schema, value)
    if isinstance(value, list):
        return _array_ok(schema, value)
    return _scalar_ok(schema, value)


def _object_ok(schema: Schema, value: dict[str, JsonValue]) -> bool:
    if schema.type not in {None, "object"}:
        return False
    if any(name not in value for name in schema.required):
        return False
    return all(
        conforms(sub, value[name]) for name, sub in schema.properties.items() if name in value
    )


def _array_ok(schema: Schema, value: list[JsonValue]) -> bool:
    if schema.type not in {None, "array"}:
        return False
    if schema.min_items is not None and len(value) < schema.min_items:
        return False
    if schema.max_items is not None and len(value) > schema.max_items:
        return False
    return schema.items is None or all(conforms(schema.items, item) for item in value)
