"""Candidatos de campo proibido da atribuição em massa, tirados do OpenAPI (ADR 0040).

Para cada operação de escrita, junta a lista declarada em `authz.mass_assignment_fields` com
campos que o próprio contrato sugere: o que o esquema de entrada marca `readOnly`, o que só
aparece na resposta da família do recurso e o que o corpo de entrada já declara com nome de
privilégio. Também escolhe o valor de teste pelo tipo e pelo valor atual do recurso, sempre
determinístico e nunca numa direção que tranque a conta. Dono do recurso (`ownership`) nunca é
derivado: só vale se declarado. Este módulo é puro e não envia nada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, Schema, effective_type, flatten_schema
from harness_dast.domain.authz_config import AuthzConfig, normalize_field_name
from harness_dast.domain.authz_fields import (
    KIND_ORDER,
    CandidateKind,
    CandidateSource,
    classify_candidate,
    is_excluded_name,
)
from harness_dast.domain.zap_alert import Severity

POST_MAX_CANDIDATES: Final = 4
"""Derivados testados por `POST` (cada um deixa um recurso criado no alvo)."""
_POST_KINDS: Final[frozenset[CandidateKind]] = frozenset({"privilege", "balance", "price", "state"})
_SOURCE_ORDER: Final[tuple[CandidateSource, ...]] = (
    "declared",
    "readonly_in_input",
    "response_only",
    "name_in_input",
)
_HIGH_KINDS: Final[frozenset[CandidateKind]] = frozenset({"privilege", "balance"})
_SCALARS: Final = frozenset({"string", "integer", "number", "boolean"})


@dataclass(frozen=True)
class Candidate:
    """Um campo a testar numa operação de escrita.

    Attributes:
        name: Nome do campo no corpo JSON.
        source: De onde veio (`declared` sempre entra).
        kind: Classe pelo nome (`other` quando a lista fixa não o conhece).
        schema: Esquema do campo (já achatado), ou `None` se o contrato não o descreve.
        declared_value: Valor declarado no perfil (só para `declared`).
    """

    name: str
    source: CandidateSource
    kind: CandidateKind
    schema: Schema | None = None
    declared_value: str | int | bool | None = None


@dataclass(frozen=True)
class Injection:
    """Campo extra e valor de teste que vão no corpo."""

    name: str
    value: JsonValue


@dataclass(frozen=True)
class CandidatePlan:
    """Candidatos finais de uma operação e quantos derivados ficaram de fora do limite.

    Attributes:
        candidates: Declarados (na ordem declarada) e depois derivados por prioridade.
        cut: Derivados cortados por `max_derived_candidates` (ou pelo teto do `POST`).
    """

    candidates: tuple[Candidate, ...]
    cut: int = 0


def _segments(path: str) -> list[str]:
    return [item for item in path.split("/") if item]


def _is_marker(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def family_key(path: str) -> str:
    """Chave da família do recurso: o caminho sem os marcadores finais.

    `/api/medicos` e `/api/medicos/{id}` têm a mesma chave; marcadores no meio viram `{}` para
    que `/a/{x}/b` e `/a/{y}/b` coincidam sem juntar `/a/{x}/b` com `/a`.
    """
    parts = _segments(path)
    while parts and _is_marker(parts[-1]):
        parts.pop()
    return "/" + "/".join("{}" if _is_marker(part) else part for part in parts)


def path_tail(path: str) -> str | None:
    """Último segmento literal do caminho (`medicos` em `/api/medicos/{id}`), ou `None`."""
    literal = [part for part in _segments(path) if not _is_marker(part)]
    return literal[-1] if literal else None


def family_of(operation: Operation, operations: Sequence[Operation]) -> tuple[Operation, ...]:
    """Operações do OpenAPI de mesma família que `operation` (ela própria inclusa)."""
    key = family_key(operation.path)
    return tuple(item for item in operations if family_key(item.path) == key)


def _root_fields(schema: Schema | None) -> dict[str, Schema]:
    """Campos de primeiro nível do objeto, do item de uma lista ou do item da lista do envelope.

    Um objeto com uma propriedade lista de objetos (`{items: [...], total, limit}`) é um envelope
    de paginação: valem os campos do item, não os de controle.
    """
    if schema is None:
        return {}
    flat = flatten_schema(schema)
    if flat.items is not None:
        flat = flatten_schema(flat.items)
    for sub in flat.properties.values():
        inner = flatten_schema(sub)
        if inner.items is not None and effective_type(flatten_schema(inner.items)) == "object":
            return dict(flatten_schema(inner.items).properties)
    return dict(flat.properties)


def _input_fields(operation: Operation) -> dict[str, Schema]:
    body = operation.request_body.preferred() if operation.request_body is not None else None
    if body is None or body.body_schema is None:
        return {}
    return dict(flatten_schema(body.body_schema).properties)


def _response_fields(family: Sequence[Operation]) -> dict[str, Schema]:
    found: dict[str, Schema] = {}
    for item in family:
        for response in item.success_responses:
            for name, sub in _root_fields(response.body_schema).items():
                found.setdefault(name, sub)
    return found


def _is_scalar(schema: Schema | None) -> bool:
    return schema is None or effective_type(flatten_schema(schema)) in (_SCALARS | {None})


def _derive(
    name: str, schema: Schema, source: CandidateSource, tail: str | None
) -> Candidate | None:
    flat = flatten_schema(schema)
    if is_excluded_name(name, tail) or not _is_scalar(flat) or effective_type(flat) is None:
        return None
    kind = classify_candidate(name)
    if kind == "ownership":
        return None
    if kind is None and source == "name_in_input":
        return None
    return Candidate(name=name, source=source, kind=kind or "other", schema=flat)


def _derived(operation: Operation, family: Sequence[Operation]) -> list[Candidate]:
    inputs = _input_fields(operation)
    outputs = _response_fields(family)
    tail = path_tail(operation.path)
    found: list[Candidate | None] = []
    for name, schema in inputs.items():
        source: CandidateSource = (
            "readonly_in_input" if flatten_schema(schema).read_only else "name_in_input"
        )
        found.append(_derive(name, schema, source, tail))
    found.extend(
        _derive(name, schema, "response_only", tail)
        for name, schema in outputs.items()
        if name not in inputs
    )
    return [item for item in found if item is not None]


def _sort_key(item: Candidate) -> tuple[int, int, str]:
    return (KIND_ORDER.index(item.kind), _SOURCE_ORDER.index(item.source), item.name)


def build_candidates(
    operation: Operation | None,
    family: Sequence[Operation],
    config: AuthzConfig,
    *,
    post: bool = False,
) -> CandidatePlan:
    """Candidatos de uma operação: declarados e depois derivados por prioridade.

    A ordem dos derivados é a da classe (`privilege`, `balance`, `price`, `state`, `other`), depois
    a da origem (`readonly_in_input`, `response_only`, `name_in_input`) e por fim o nome. Nome
    repetido (comparado normalizado: `isAdmin` = `is_admin`) fica só uma vez e o declarado vence.
    Os derivados ficam limitados a `config.max_derived_candidates`; no `POST` entram só os de
    classe conhecida e no máximo `POST_MAX_CANDIDATES`.

    Args:
        operation: Operação do OpenAPI, ou `None` se não foi achada (só os declarados).
        family: Operações da mesma família (veja `family_of`).
        config: Bloco `authz` do perfil.
        post: Se a operação cria recurso.

    Returns:
        Os candidatos e quantos derivados foram cortados.
    """
    declared = tuple(
        Candidate(
            name=item.name,
            source="declared",
            kind=classify_candidate(item.name) or "other",
            declared_value=item.value,
        )
        for item in config.mass_assignment_fields
    )
    if operation is None or not config.derive_mass_candidates:
        return CandidatePlan(declared)
    taken = {normalize_field_name(item.name) for item in declared}
    unique: dict[str, Candidate] = {}
    for item in sorted(_derived(operation, family), key=_sort_key):
        key = normalize_field_name(item.name)
        if key not in taken and key not in unique:
            unique[key] = item
    pool = list(unique.values())
    limit = config.max_derived_candidates
    if post:
        pool = [item for item in pool if item.kind in _POST_KINDS]
        limit = min(limit, POST_MAX_CANDIDATES)
    kept = pool[:limit]
    return CandidatePlan((*declared, *kept), len(pool) - len(kept))


def mass_severity(source: CandidateSource, kind: CandidateKind) -> Severity:
    """Severidade do achado: alta para `declared`, `privilege` e `balance`; média nos demais."""
    return "high" if source == "declared" or kind in _HIGH_KINDS else "medium"
