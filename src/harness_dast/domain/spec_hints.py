"""Hipóteses limitadas para encadeamento e uso de contas pares no probe."""

import re
from collections import defaultdict
from collections.abc import Sequence

from harness_dast.domain.api_model import Operation, safe_identifier
from harness_dast.domain.api_schema import ApiModel, Schema, effective_type, flatten_schema
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.profile import ProductProfile

MAX_HINTS = 40
MAX_OPERATIONS = 250
MAX_SCHEMA_NODES = 100
MAX_DEPTH = 5
_WORDS = re.compile(r"[^a-z0-9]")
_FILE_NAMES = frozenset({"arquivo", "filename", "file", "nomearquivo"})


class SpecHint(ApiModel):
    """Hipótese que uma pessoa ou agente deve conferir antes de alterar o perfil."""

    kind: str
    message: str
    producer: str | None = None
    field: str | None = None
    consumer: str | None = None
    parameter: str | None = None
    role: str | None = None
    accounts: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()


def _key(value: str) -> str:
    return _WORDS.sub("", value.lower())


def _fields(schema: Schema) -> list[tuple[str, Schema]]:
    """Visita caminhos escalares de coleções sem ultrapassar os tetos."""
    stack = [(schema, "", 0, False)]
    result: list[tuple[str, Schema]] = []
    visited = 0
    while stack and visited < MAX_SCHEMA_NODES:
        node, path, depth, in_list = stack.pop()
        visited += 1
        if depth > MAX_DEPTH or node.truncated:
            continue
        node = flatten_schema(node)
        if node.items is not None and effective_type(node) == "array":
            stack.append((node.items, f"{path}.0" if path else "0", depth + 1, True))
        elif node.properties:
            for name, child in list(node.properties.items())[:MAX_SCHEMA_NODES]:
                stack.append((child, f"{path}.{name}" if path else name, depth + 1, in_list))
        elif in_list and effective_type(node) in {"string", "integer"}:
            result.append((path, node))
    return result


def _link_hint(source: Operation, field: str, target: Operation, parameter: str) -> SpecHint:
    return SpecHint(
        kind="flow",
        producer=source.operation_id,
        field=field,
        consumer=target.operation_id,
        parameter=parameter,
        message=(
            f"Hipótese: {safe_identifier(source.operation_id)} pode fornecer o campo "
            f"{safe_identifier(field)} para o parâmetro {safe_identifier(parameter)} de "
            f"{safe_identifier(target.operation_id)}. Confira o contrato e os dados antes "
            "de configurar flows.yml; uma lista vazia não fornece valor."
        ),
    )


def _targets(readers: Sequence[Operation]) -> dict[str, list[tuple[Operation, str, Schema]]]:
    targets: dict[str, list[tuple[Operation, str, Schema]]] = defaultdict(list)
    for operation in readers:
        for param in operation.parameters:
            if param.required and param.location in {"path", "query"}:
                targets[_key(param.name)].append((operation, param.name, param.value_schema))
                flat = flatten_schema(param.value_schema)
                if flat.format in {"uuid"}:
                    targets["format:" + flat.format].append(
                        (operation, param.name, param.value_schema)
                    )
    return targets


def _matches(
    source: Operation, field: Schema, path: str, target: Operation, param: Schema, key: str
) -> bool:
    if source.operation_id == target.operation_id:
        return False
    param = flatten_schema(param)
    if effective_type(field) != effective_type(param):
        return False
    if field.format and param.format and field.format != param.format:
        return False
    if path == "0" or key.startswith("format:"):
        return target.path.startswith(source.path.rstrip("/") + "/")
    return True


def _field_keys(path: str, schema: Schema) -> set[str]:
    keys = {_key(path.rsplit(".", 1)[-1])}
    if schema.format == "uuid":
        keys.add("format:uuid")
    if path == "0" and effective_type(schema) == "string":
        keys |= _FILE_NAMES
    return keys


def _flow_hints(operations: Sequence[Operation]) -> list[SpecHint]:
    readers = [op for op in operations if op.method == "get"][:MAX_OPERATIONS]
    targets = _targets(readers)
    hints: list[SpecHint] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source in readers:
        schema = source.success_schema()
        if schema is None:
            continue
        for path, field_schema in _fields(schema):
            for key in sorted(_field_keys(path, field_schema)):
                for target, name, param_schema in targets.get(key, ())[:MAX_HINTS]:
                    if not _matches(source, field_schema, path, target, param_schema, key):
                        continue
                    identity = (source.operation_id, path, target.operation_id, name)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    hints.append(_link_hint(source, path, target, name))
                    if len(hints) >= MAX_HINTS:
                        return hints
    return hints


def _object_read(operation: Operation) -> bool:
    return operation.method == "get" and (
        bool(operation.path_placeholders)
        or any(p.required and _key(p.name).endswith("id") for p in operation.parameters)
    )


def _account_hints(profile: ProductProfile, operations: Sequence[Operation]) -> list[SpecHint]:
    by_role: dict[str, list[str]] = defaultdict(list)
    for account in profile.auth.accounts:
        by_role[account.role].append(account.alias)
    by_account: dict[str, list[str]] = defaultdict(list)
    for op in [item for item in operations if item.method == "get"][:MAX_OPERATIONS]:
        if _object_read(op):
            by_account[profile.account_for(op.operation_id, op.method, op.path)].append(
                op.operation_id
            )
    result: list[SpecHint] = []
    for role, aliases in by_role.items():
        if role in profile.authz.shared_roles or len(aliases) < 2:
            continue
        assigned = [alias for alias in aliases if by_account[alias]]
        if len(assigned) != 1:
            continue
        owner = assigned[0]
        reads = tuple(by_account[owner])
        guidance = (
            "Considere distribuir leituras de objeto entre duas contas deste papel "
            "não compartilhado, "
            "em operações distintas, se o dono confirmar "
            "que cada uma pode acessá-las."
            if len(reads) > 1
            else "Há apenas uma operação candidata: account_map aceita uma conta por operação."
        )
        result.append(
            SpecHint(
                kind="peer_account",
                role=role,
                accounts=tuple(aliases),
                operations=reads,
                message=(
                    f"Hipótese: as leituras de objeto do papel {safe_identifier(role)} estão "
                    f"roteadas só para {safe_identifier(owner)}, embora haja conta par. {guidance} "
                    "O teste entre contas depende de pedidos bem-sucedidos e das permissões reais."
                ),
            )
        )
        if len(result) >= MAX_HINTS:
            break
    return result


def suggest_spec_hints(
    profile: ProductProfile, operations: Sequence[Operation], plan: Sequence[PlannedOperation]
) -> tuple[SpecHint, ...]:
    """Sugere hipóteses sem tocar o alvo nem alterar o perfil; só inclui operações permitidas."""
    allowed = {item.operation_id for item in plan if item.decision == "send"}
    eligible = [operation for operation in operations if operation.operation_id in allowed]
    accounts = _account_hints(profile, eligible)
    return tuple((accounts + _flow_hints(eligible))[:MAX_HINTS])
