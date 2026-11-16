"""Dicas de conflito e dependências bloqueadas, sem valores de requisição."""

import re
from collections.abc import Mapping, Sequence

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, Schema, flatten_schema
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.outcome import parse_json_body
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult

_SAFE_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,59}\Z")


def _fields(
    schema: Schema, body: JsonValue, prefix: str = "", *, restricted: bool = False
) -> set[str]:
    flat = flatten_schema(schema)
    if flat.read_only:
        return set()
    if isinstance(body, list) and flat.items is not None:
        return {
            name
            for index, value in enumerate(body)
            for name in _fields(flat.items, value, f"{prefix}[{index}]", restricted=restricted)
        }
    if not isinstance(body, dict):
        return set()
    result: set[str] = set()
    for name, raw in flat.properties.items():
        if name not in body or not _SAFE_FIELD.fullmatch(name):
            continue
        path = f"{prefix}.{name}" if prefix else name
        item = flatten_schema(raw)
        if item.read_only or len(path) > 60:
            continue
        if item.properties or item.items is not None:
            result.update(_fields(item, body[name], path, restricted=restricted))
        elif not restricted or (
            name in flat.required and (item.pattern or item.format or item.max_length is not None)
        ):
            result.add(path)
    return result


def conflict_fields(
    response: HttpResponse, operation: Operation, body: JsonValue, generated: Mapping[str, bool]
) -> tuple[str, ...]:
    """Identifica nomes do corpo citados no erro, ou candidatos gerados e restritos.

    A resposta só pode indicar nomes presentes no corpo; não retorna valores nem texto livre.
    """
    parsed = parse_json_body(response)
    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    media = operation.request_body.preferred() if operation.request_body else None
    if media is None or media.body_schema is None:
        return ()
    names = _fields(media.body_schema, body)
    if isinstance(errors, list):
        fields = tuple(
            dict.fromkeys(
                item["field"]
                for item in errors
                if isinstance(item, dict)
                and isinstance(item.get("field"), str)
                and item["field"] in names
            )
        )
        if fields:
            return fields
    return tuple(
        name
        for name in sorted(_fields(media.body_schema, body, restricted=True))
        if f"body.{name}" in generated and not generated[f"body.{name}"]
    )


def annotate_blocked(
    results: Sequence[OperationResult], plan: Sequence[PlannedOperation]
) -> tuple[OperationResult, ...]:
    """Conta consumidores efetivamente pulados por dependências transitivas sem duplicar."""
    by_id = {item.operation_id: item for item in results}
    dependencies = {item.operation_id: item.depends_on for item in plan}
    blocked: dict[str, set[str]] = {}
    for item in results:
        if item.outcome != "skipped_dependency":
            continue
        pending = list(dependencies.get(item.operation_id, ()))
        seen: set[str] = set()
        while pending:
            producer = pending.pop()
            if producer in seen or producer not in by_id or by_id[producer].outcome == "success":
                continue
            seen.add(producer)
            blocked.setdefault(producer, set()).add(item.operation_id)
            if by_id[producer].outcome == "skipped_dependency":
                pending.extend(dependencies.get(producer, ()))
    return tuple(
        item.model_copy(update={"blocked_dependencies": len(blocked.get(item.operation_id, ()))})
        for item in results
    )
