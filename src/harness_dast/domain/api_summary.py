"""Resumo compacto e determinístico da API para o agente, com tamanho máximo garantido.

O agente lê este resumo (e não o OpenAPI inteiro) para escrever `data-rules.yml` e
`flows.yml`. Por operação: identificador, método, caminho, entradas OBRIGATÓRIAS com tipo e
restrições, quantas entradas opcionais existem e quais campos parecem identificadores
produzidos (na resposta) ou consumidos (na entrada). Um orçamento em caracteres do JSON
impede que uma API enorme inunde o contexto do agente: o que não couber é contado em
`omitted_operations`. Os textos vêm do documento (não confiáveis) e são cortados. Este
módulo é puro.
"""

import re

from pydantic import Field

from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.api_schema import (
    ApiModel,
    Schema,
    effective_type,
    flatten_schema,
)

DEFAULT_BUDGET_CHARS = 40_000
MIN_BUDGET_CHARS = 2_000
MAX_BUDGET_CHARS = 200_000
MAX_INPUTS_PER_OPERATION = 40
MAX_DEPTH = 4
MAX_PRODUCED = 10
_TEXT = 60
_CONSTRAINT = 80
_SLACK = 400
_ID_NAME = re.compile(
    r"^(?i:id|uuid|guid)$|[_\-.](?i:id|uuid|guid)$|[a-z0-9](?:Id|ID|Uuid|UUID|Guid|GUID)$"
)
type _Entry = tuple[InputSummary, bool]


def looks_like_identifier(name: str, schema: Schema) -> bool:
    """Heurística: o campo parece um identificador (`id`, `user_id`, `pacienteId`, uuid)?

    Só uma dica para o agente; nenhuma decisão do harness depende dela.
    """
    return schema.format == "uuid" or _ID_NAME.search(name) is not None


def _cut(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


class InputSummary(ApiModel):
    """Uma entrada obrigatória de uma operação.

    Attributes:
        where: `path`, `query`, `header`, `cookie` ou `body`.
        name: Nome (campos de corpo aninhados usam pontos; listas, `[]`).
        type: Tipo e formato (`string/uuid`, `array<integer>`).
        constraints: Restrições em texto curto (`len 3..20; enum a|b`).
    """

    where: str
    name: str
    type: str
    constraints: str = ""


class OperationSummary(ApiModel):
    """Resumo de uma operação.

    Attributes:
        id: `operation_id`.
        method: Método HTTP em maiúsculas.
        path: Modelo de caminho.
        auth: Exige algum esquema de segurança.
        deprecated: Marcada como obsoleta.
        inputs: Entradas obrigatórias (até 40).
        more_inputs: Entradas obrigatórias que não couberam em `inputs`.
        optional_inputs: Quantidade de entradas opcionais (não listadas).
        produces: Campos da resposta que parecem identificadores.
        consumes: Entradas obrigatórias que parecem identificadores.
    """

    id: str
    method: str
    path: str
    auth: bool = False
    deprecated: bool = False
    inputs: tuple[InputSummary, ...] = ()
    more_inputs: int = 0
    optional_inputs: int = 0
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()


class ApiSummary(ApiModel):
    """Resumo da API inteira.

    Attributes:
        title: Título (cortado).
        version: Versão (cortada).
        operation_count: Total de operações da API.
        omitted_operations: Operações que não couberam no orçamento (as últimas).
        operations: Operações resumidas, na ordem do documento.
    """

    title: str
    version: str
    operation_count: int
    omitted_operations: int = Field(ge=0)
    operations: tuple[OperationSummary, ...]


def _type_text(schema: Schema) -> str:
    flat = flatten_schema(schema)
    kind = effective_type(flat) or "any"
    if kind == "array" and flat.items is not None:
        return f"array<{_type_text(flat.items)}>"
    return f"{kind}/{flat.format}" if flat.format else kind


def _constraints(schema: Schema) -> str:
    flat = flatten_schema(schema)
    parts: list[str] = []
    if flat.enum:
        parts.append("enum " + "|".join(str(v) for v in flat.enum[:5]))
    if flat.minimum is not None or flat.maximum is not None:
        parts.append(f"range {_bound(flat.minimum)}..{_bound(flat.maximum)}")
    if flat.min_length is not None or flat.max_length is not None:
        parts.append(f"len {flat.min_length or 0}..{_bound(flat.max_length)}")
    if flat.pattern:
        parts.append("pattern " + flat.pattern)
    return _cut("; ".join(parts), _CONSTRAINT)


def _bound(value: float | None) -> str:
    return "" if value is None else str(value)


def _body_inputs(schema: Schema, prefix: str, depth: int) -> tuple[list[_Entry], int]:
    """Entradas obrigatórias do corpo e a contagem de campos opcionais (até `MAX_DEPTH`)."""
    flat = flatten_schema(schema)
    if depth >= MAX_DEPTH:
        return [], 0
    if flat.items is not None:
        return _body_inputs(flat.items, prefix + "[]", depth + 1)
    required: list[_Entry] = []
    optional = 0
    for name, sub in flat.properties.items():
        full = f"{prefix}.{name}" if prefix else name
        if flatten_schema(sub).read_only:
            continue
        if name not in flat.required:
            optional += 1
            continue
        child = flatten_schema(sub)
        if child.properties or child.items is not None:
            inner, inner_optional = _body_inputs(sub, full, depth + 1)
            required.extend(inner)
            optional += inner_optional
        else:
            required.append(_input("body", full, sub))
    return required, optional


def _input(where: str, name: str, schema: Schema) -> _Entry:
    summary = InputSummary(
        where=where,
        name=_cut(name, _TEXT),
        type=_cut(_type_text(schema), _TEXT),
        constraints=_constraints(schema),
    )
    return summary, looks_like_identifier(name.rsplit(".", 1)[-1], flatten_schema(schema))


def _produced(schema: Schema | None, prefix: str, depth: int) -> list[str]:
    if schema is None or depth >= MAX_DEPTH:
        return []
    flat = flatten_schema(schema)
    if flat.items is not None:
        return _produced(flat.items, prefix + "[]" if prefix else "[]", depth + 1)
    found: list[str] = []
    for name, sub in flat.properties.items():
        full = f"{prefix}.{name}" if prefix else name
        if looks_like_identifier(name, flatten_schema(sub)):
            found.append(_cut(full, _TEXT))
        found.extend(_produced(sub, full, depth + 1))
    return found


def summarize_operation(operation: Operation) -> OperationSummary:
    """Resume uma operação (entradas obrigatórias, contagem de opcionais, ids)."""
    inputs = [
        _input(p.location, p.name, p.value_schema) for p in operation.parameters if p.required
    ]
    optional = sum(1 for p in operation.parameters if not p.required)
    media = operation.request_body.preferred() if operation.request_body else None
    if media is not None and media.body_schema is not None:
        body, body_optional = _body_inputs(media.body_schema, "", 0)
        inputs.extend(body)
        optional += body_optional
    consumes = tuple(item.name for item, is_id in inputs if is_id)
    return OperationSummary(
        id=_cut(operation.operation_id, 120),
        method=operation.method.upper(),
        path=_cut(operation.path, 120),
        auth=operation.requires_auth,
        deprecated=operation.deprecated,
        inputs=tuple(item for item, _ in inputs[:MAX_INPUTS_PER_OPERATION]),
        more_inputs=max(len(inputs) - MAX_INPUTS_PER_OPERATION, 0),
        optional_inputs=optional,
        produces=tuple(_produced(operation.success_schema(), "", 0)[:MAX_PRODUCED]),
        consumes=consumes[:MAX_PRODUCED],
    )


def summarize(spec: ApiSpec, budget_chars: int = DEFAULT_BUDGET_CHARS) -> ApiSummary:
    """Resume a API respeitando um orçamento rígido de tamanho.

    Args:
        spec: A API normalizada.
        budget_chars: Teto, em caracteres, do JSON do resumo (`model_dump_json`); no mínimo
            2000 (valores menores são elevados a 2000).

    Returns:
        O resumo. Garantia: `len(summary.model_dump_json()) <= budget_chars`. As operações
        que não couberem (as últimas do documento) são contadas em `omitted_operations`.
    """
    budget = max(budget_chars, MIN_BUDGET_CHARS)
    used = _SLACK
    shown: list[OperationSummary] = []
    for operation in spec.operations:
        item = summarize_operation(operation)
        size = len(item.model_dump_json()) + 1
        if used + size > budget:
            break
        used += size
        shown.append(item)
    return ApiSummary(
        title=_cut(spec.title, _TEXT),
        version=_cut(spec.version, _TEXT),
        operation_count=len(spec.operations),
        omitted_operations=len(spec.operations) - len(shown),
        operations=tuple(shown),
    )
