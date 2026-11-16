"""Escolha genérica de campo textual para marcador de uma criação autorizada."""

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import Schema, flatten_schema
from harness_dast.domain.authz_config import normalize_field_name
from harness_dast.domain.authz_fields import classify_candidate, is_excluded_name


def _plain_text(schema: Schema, *, writable: bool = False) -> bool:
    field = flatten_schema(schema)
    return (
        not field.truncated
        and field.type == "string"
        and (not writable or not field.read_only)
        and field.enum is None
        and field.format is None
        and field.pattern is None
    )


def marker_fields(
    post: Operation | None, read: Operation | None, bound: frozenset[str]
) -> tuple[tuple[str, int, int | None], ...]:
    """Campos comuns simples, sem referências vinculadas, e limites do corpo de entrada."""
    if post is None or read is None or post.request_body is None:
        return ()
    body = post.request_body.preferred()
    if body is None or body.body_schema is None:
        return ()
    inputs = flatten_schema(body.body_schema)
    if inputs.truncated or inputs.type != "object":
        return ()
    outputs = _output_fields(read)
    candidates = []
    for name, field in inputs.properties.items():
        output = outputs.get(name)
        if (
            is_excluded_name(name, None)
            or classify_candidate(name) is not None
            or normalize_field_name(name).endswith("id")
        ):
            continue
        if output is None or not _plain_text(field, writable=True) or not _plain_text(output):
            continue
        if any(path == name or path.startswith(name + ".") for path in bound):
            continue
        flat = flatten_schema(field)
        result = flatten_schema(output)
        minimum = max(flat.min_length or 0, result.min_length or 0)
        maxima = [value for value in (flat.max_length, result.max_length) if value is not None]
        candidates.append((name, minimum, min(maxima) if maxima else None))
    return tuple(candidates)


def _output_fields(read: Operation) -> dict[str, Schema]:
    outputs: dict[str, Schema] = {}
    for response in read.success_responses:
        if response.body_schema is not None:
            schema = flatten_schema(response.body_schema)
            if not schema.truncated and schema.type == "object":
                outputs.update(schema.properties)
    return outputs
