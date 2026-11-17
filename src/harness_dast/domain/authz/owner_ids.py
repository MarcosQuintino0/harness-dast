"""Identidades observadas de dono, sem adivinhação ou persistência de respostas."""

import re
from collections.abc import Sequence

from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.api_schema import JsonValue, Schema, effective_type, flatten_schema
from harness_dast.domain.authz.compare import is_success_status
from harness_dast.domain.authz.config import normalize_field_name
from harness_dast.domain.authz.created import parse_unique_json
from harness_dast.domain.authz.pair_inventory import MAX_INVENTORY_ITEMS
from harness_dast.domain.authz.sensitive import classify_field_name
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.schema_check import violations

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def owner_parameter(operation: Operation) -> Parameter | None:
    """Aceita um único marcador final escalar, sem outros parâmetros obrigatórios."""
    markers = operation.path_placeholders
    if len(markers) != 1 or not operation.path.endswith("/{" + markers[0] + "}"):
        return None
    params = [p for p in operation.parameters if p.location == "path" and p.name == markers[0]]
    if len(params) != 1:
        return None
    parameter = params[0]
    schema = flatten_schema(parameter.value_schema)
    if schema.truncated or effective_type(schema) not in {"string", "integer"}:
        return None
    if classify_field_name(parameter.name) == "secret":
        return None
    if any(p.required and p != parameter for p in operation.parameters):
        return None
    return parameter


def owner_identity(value: JsonValue, parameter: Parameter) -> str | None:
    """Identidade canônica, do tipo declarado e segura como segmento simples de caminho."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    if violations(flatten_schema(parameter.value_schema), value):
        return None
    text = str(value)
    return text if _SAFE_ID.fullmatch(text) else None


def object_identity(value: JsonValue, parameter: Parameter) -> str | None:
    """Extrai campo do parâmetro ou id; identidades contraditórias/normalizadas recusam."""
    if not isinstance(value, dict):
        return None
    names = {normalize_field_name(parameter.name), "id"}
    found: dict[str, str] = {}
    for name, item in value.items():
        normalized = normalize_field_name(name)
        if normalized not in names:
            continue
        identity = owner_identity(item, parameter)
        if normalized in found or identity is None:
            return None
        found[normalized] = identity
    identities = set(found.values())
    return next(iter(identities)) if len(identities) == 1 else None


def owner_inventory(body: bytes, parameter: Parameter) -> tuple[str, ...] | None:
    """Coleção inteira válida e ordenada, vazia ou None se ambígua/malformada."""
    parsed = parse_unique_json(body)
    if not isinstance(parsed, list) or len(parsed) > MAX_INVENTORY_ITEMS:
        return None
    found: set[str] = set()
    for item in parsed:
        identity = object_identity(item, parameter)
        if identity is None or identity in found:
            return None
        found.add(identity)
    return tuple(sorted(found))


def owner_collection(operation: Operation, item: Operation, parameter: Parameter) -> bool:
    """Coleção irmã array de objetos, com identidade compatível e sem filtro obrigatório."""
    if operation.method != "get" or operation.path != item.path.rsplit("/", 1)[0]:
        return False
    if any(p.required for p in operation.parameters) or operation.request_body is not None:
        return False
    if not operation.success_responses:
        return False
    return all(
        _collection_schema(response.body_schema, parameter)
        for response in operation.success_responses
    )


def _collection_schema(schema: Schema | None, parameter: Parameter) -> bool:
    if schema is None:
        return False
    array = flatten_schema(schema)
    if array.truncated or array.type != "array" or array.items is None:
        return False
    item = flatten_schema(array.items)
    names = {normalize_field_name(parameter.name), "id"}
    return (
        not item.truncated
        and effective_type(item) == "object"
        and any(
            normalize_field_name(name) in names
            and effective_type(flatten_schema(value))
            == effective_type(flatten_schema(parameter.value_schema))
            for name, value in item.properties.items()
        )
    )


def recorded_owner_ids(
    operation: Operation, parameter: Parameter, account: str, exchanges: Sequence[ExchangeRecord]
) -> tuple[str, ...] | None:
    """IDs em alvos de sucesso da própria conta; depois JSON de criação já sanitizado.

    None recusa evidência ambígua. Não extrai ID de respostas, nunca gravadas no log.
    """
    known = [e for e in exchanges if e.account == account and is_success_status(e.status)]
    direct = [e for e in known if e.path == operation.path]
    if direct:
        values = [_target_identity(e.target, operation, parameter) for e in direct]
    else:
        posts = [
            e
            for e in known
            if e.method == "POST"
            and e.path == operation.path.rsplit("/", 1)[0]
            and e.body is not None
        ]
        values = [_post_identity(e, parameter) for e in posts]
    if any(value is None for value in values):
        return None
    return tuple(sorted({value for value in values if value is not None}))


def _target_identity(target: str, operation: Operation, parameter: Parameter) -> str | None:
    prefix = operation.path.rsplit("/", 1)[0] + "/"
    if not target.startswith(prefix) or "?" in target:
        return None
    value = target[len(prefix) :]
    if effective_type(flatten_schema(parameter.value_schema)) == "integer":
        if not re.fullmatch(r"-?(0|[1-9][0-9]{0,17})", value):
            return None
        return owner_identity(int(value), parameter)
    return owner_identity(value, parameter)


def _post_identity(exchange: ExchangeRecord, parameter: Parameter) -> str | None:
    names = {normalize_field_name(parameter.name), "id"}
    if any(normalize_field_name(name) in names for name in exchange.omitted_fields):
        return None
    return object_identity(parse_unique_json((exchange.body or "").encode()), parameter)
