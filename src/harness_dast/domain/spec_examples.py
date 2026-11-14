"""Inspeção offline dos exemplos escalares preservados no modelo de API."""

from collections.abc import Iterator

from harness_dast.domain.api_model import ApiSpec, safe_identifier
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.schema_check import check_schema

MAX_EXAMPLE_ISSUES = 100
MAX_EXAMPLE_SCHEMAS = 10000


def _schemas(spec: ApiSpec) -> Iterator[tuple[str, Schema]]:
    for op in spec.operations:
        label = safe_identifier(op.operation_id)
        for parameter in op.parameters:
            yield (
                f"operação {label}, parâmetro {safe_identifier(parameter.name)}",
                parameter.value_schema,
            )
        if op.request_body:
            for media in op.request_body.media:
                if media.body_schema:
                    yield (
                        f"operação {label}, corpo {safe_identifier(media.media_type)}",
                        media.body_schema,
                    )
        for response in op.success_responses:
            if response.body_schema:
                yield f"operação {label}, resposta {response.status}", response.body_schema


def _walk(label: str, schema: Schema) -> Iterator[tuple[str, Schema]]:
    stack = [(label, schema)]
    while stack:
        current, node = stack.pop()
        yield current, node
        children = [
            (f"{current}, campo {safe_identifier(name)}", sub)
            for name, sub in node.properties.items()
        ]
        if node.items:
            children.append((f"{current}, itens", node.items))
        for name, branches in (
            ("allOf", node.all_of),
            ("anyOf", node.any_of),
            ("oneOf", node.one_of),
        ):
            children.extend(
                (f"{current}, {name} {index + 1}", sub) for index, sub in enumerate(branches)
            )
        stack.extend(reversed(children))


def _validate_tree(schema: Schema, value: JsonValue) -> Iterator[str]:
    stack: list[tuple[Schema, JsonValue]] = [(schema, value)]
    visited = 0
    while stack:
        node, current = stack.pop()
        visited += 1
        if visited > 10000:
            yield "truncated"
            return
        yield from check_schema(node, current)
        if node.truncated:
            continue
        if isinstance(current, dict):
            stack.extend(
                (sub, current[name])
                for name, sub in reversed(tuple(node.properties.items()))
                if name in current
            )
        if isinstance(current, list) and node.items:
            stack.extend((node.items, item) for item in reversed(current))
        stack.extend((branch, current) for branch in reversed(node.all_of))


def inspect_examples(spec: ApiSpec) -> tuple[tuple[str, str], ...]:
    """Retorna localização e código, limitados e sem valores dos exemplos.

    Valida restrições locais e allOf; não avalia oneOf, anyOf, pattern ou format.
    """
    issues: list[tuple[str, str]] = []
    visited = 0
    for label, root in _schemas(spec):
        for where, schema in _walk(label, root):
            visited += 1
            if visited > MAX_EXAMPLE_SCHEMAS:
                return (*issues, ("Limite de esquemas atingido", "truncated"))
            examples = schema.declared_examples or (
                (schema.example,) if schema.example is not None else ()
            )
            for value in examples:
                for code in _validate_tree(schema, value):
                    if len(issues) == MAX_EXAMPLE_ISSUES:
                        return (*issues, ("Limite de problemas atingido", "truncated"))
                    issues.append((where, code))
    return tuple(issues)
