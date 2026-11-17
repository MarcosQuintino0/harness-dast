"""Valida o formato de inventário observável usado antes da criação de par."""

import json

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import effective_type, flatten_schema
from harness_dast.domain.authz.config import normalize_field_name
from harness_dast.domain.authz.created import created_identifier, parse_unique_json
from harness_dast.domain.probe_exchange import ExchangeRecord

MAX_INVENTORY_ITEMS = 10000


def supports_inventory(
    operation: Operation | None, reader: ExchangeRecord, markers: frozenset[str]
) -> bool:
    """Aceita somente GET sem parâmetros de consulta e resposta array sem limite declarado.

    Ausência de parâmetros não garante que o servidor não aplique filtros ou limites ocultos.
    """
    if operation is None or operation.method != "get":
        return False
    if any(item.location == "query" for item in operation.parameters):
        return False
    if not operation.success_responses:
        return False
    marker = normalize_field_name(reader.path.rsplit("/", 1)[-1].strip("{}"))
    for response in operation.success_responses:
        if response.body_schema is None:
            return False
        schema = flatten_schema(response.body_schema)
        if schema.truncated or schema.type != "array" or schema.items is None:
            return False
        if schema.max_items is not None:
            return False
        item = flatten_schema(schema.items)
        if item.truncated or item.type != "object" or not markers <= item.properties.keys():
            return False
        if not any(
            normalize_field_name(name) in {marker, "id"}
            and effective_type(flatten_schema(value)) in {"string", "integer"}
            for name, value in item.properties.items()
        ):
            return False
    return True


def inventory_ids(
    body: bytes, reader: ExchangeRecord, base_url: str, markers: dict[str, str]
) -> frozenset[str] | None:
    """Extrai IDs ou recusa coleção malformada ou com marcador pré-existente."""
    items = parse_unique_json(body)
    if not isinstance(items, list) or len(items) > MAX_INVENTORY_ITEMS:
        return None
    found: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            return None
        if not markers.keys() <= item.keys():
            return None
        if any(item.get(name) == value for name, value in markers.items()):
            return None
        identifier = created_identifier(
            location=None, body=json.dumps(item).encode(), reader=reader, base_url=base_url
        )
        if identifier is None or identifier in found:
            return None
        found.add(identifier)
    return frozenset(found)
