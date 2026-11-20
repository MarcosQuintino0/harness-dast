"""Identificador de objeto de um pedido provado: no caminho e na consulta (ADR 0042).

O BOLA repete com outra conta do mesmo papel um `GET` que o `probe` já provou. Este módulo diz,
só pelos dados do pedido e do OpenAPI, quais partes do pedido identificam um objeto: os
marcadores `{id}` do caminho e os parâmetros de CONSULTA que passam em quatro condições (existem
no OpenAPI, têm nome de identificador ou foram declarados em `authz.id_parameters`, têm esquema
de identificador e o valor enviado tem forma de identificador). Nada é inventado: o valor testado
é o que o `probe` enviou. Identificador no corpo fica fora desta versão. Este módulo é puro e nunca
levanta por entrada malformada: o que não se entende vira `ambiguous` ou é ignorado.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal
from urllib.parse import unquote

from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz.config import DEFAULT_VOLATILE_FIELDS, normalize_field_name
from harness_dast.domain.authz.sensitive import field_words
from harness_dast.domain.probe_exchange import ExchangeRecord

IdentifierWhere = Literal["path", "query"]
IdentifierConfidence = Literal["owned_hint", "name_only"]

ID_WORDS: Final = frozenset({"id", "uuid", "guid"})
NOT_IDENTIFIERS: Final = frozenset({*DEFAULT_VOLATILE_FIELDS, "sessionid"})
"""Nomes (normalizados) que terminam em `id`, mas não identificam objeto."""
MAX_TEXT_ID: Final = 64
_DIGITS = re.compile(r"[0-9]{1,18}")
_UUID = re.compile(r"[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{6,64}")
_MARKER = re.compile(r"\{([^{}/]+)\}")


@dataclass(frozen=True)
class IdentifierRef:
    """Um identificador de objeto de um pedido.

    Attributes:
        where: `path` (marcador do modelo de caminho) ou `query` (parâmetro de consulta).
        name: Nome do marcador ou do parâmetro.
        confidence: Só na consulta. `owned_hint`: o mesmo valor aparece como identificador de
            caminho em outro pedido provado da mesma conta (evidência de que o objeto é dela);
            `name_only`: só o nome indica identificador. `None` no caminho.
    """

    where: IdentifierWhere
    name: str
    confidence: IdentifierConfidence | None = None


@dataclass(frozen=True)
class IdentifierScan:
    """O que `find_identifiers` achou num pedido.

    Attributes:
        refs: Identificadores reconhecidos (caminho primeiro, depois consulta por nome).
        ambiguous: Nomes de consulta que passariam, mas o valor é vazio, em lista, repetido ou sem
            forma de identificador (`ambiguous_identifier`).
    """

    refs: tuple[IdentifierRef, ...] = ()
    ambiguous: tuple[str, ...] = ()

    @property
    def query_refs(self) -> tuple[IdentifierRef, ...]:
        """Só os identificadores da consulta."""
        return tuple(ref for ref in self.refs if ref.where == "query")


def is_identifier_name(name: str, extra_names: Sequence[str] = ()) -> bool:
    """Nome de identificador: última palavra `id`, `uuid` ou `guid`, ou nome declarado."""
    if name in extra_names:
        return True
    if normalize_field_name(name) in NOT_IDENTIFIERS:
        return False
    words = field_words(name)
    return bool(words) and words[-1] in ID_WORDS


def _schema_fits(schema: Schema) -> bool:
    if schema.enum:
        return False
    if schema.type == "integer":
        return True
    if schema.type != "string":
        return False
    return schema.format == "uuid" or schema.max_length is None or schema.max_length <= MAX_TEXT_ID


def _value_fits(value: str, schema: Schema) -> bool:
    if schema.type == "integer":
        return _DIGITS.fullmatch(value) is not None
    return any(pattern.fullmatch(value) for pattern in (_DIGITS, _UUID, _TOKEN))


def query_pairs(target: str) -> list[tuple[str, str]]:
    """Pares (nome, valor bruto) da consulta de um alvo; parte malformada é pulada, sem erro."""
    query = target.partition("?")[2]
    pairs: list[tuple[str, str]] = []
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name:
            pairs.append((unquote(name), value))
    return pairs


def _owned_values(exchange: ExchangeRecord, others: Sequence[ExchangeRecord]) -> frozenset[str]:
    """Valores de identificador de caminho de outros pedidos provados da mesma conta."""
    found: set[str] = set()
    for other in others:
        if other.account != exchange.account or "{" not in other.path:
            continue
        template = other.path.split("/")
        concrete = other.target.partition("?")[0].split("/")
        if len(template) != len(concrete):
            continue
        found.update(c for t, c in zip(template, concrete, strict=True) if _MARKER.fullmatch(t))
    return frozenset(found)


def _query_ref(
    parameter: Parameter, value: str, repeated: bool, owned: frozenset[str]
) -> IdentifierRef | None:
    if repeated or not value or not _value_fits(value, parameter.value_schema):
        return None
    return IdentifierRef("query", parameter.name, "owned_hint" if value in owned else "name_only")


def find_identifiers(
    operation: Operation | None,
    exchange: ExchangeRecord,
    others: Sequence[ExchangeRecord] = (),
    extra_names: Sequence[str] = (),
) -> IdentifierScan:
    """Identificadores de objeto de um pedido provado.

    Args:
        operation: Operação do OpenAPI (sem ela, só o caminho vale).
        exchange: O pedido provado.
        others: Todos os pedidos provados (fonte do `owned_hint`).
        extra_names: `authz.id_parameters`: nomes de consulta declarados como identificador.

    Returns:
        Os identificadores e os nomes ambíguos. Nunca levanta por alvo malformado.
    """
    path = [IdentifierRef("path", name) for name in _MARKER.findall(exchange.path)]
    declared = (
        {p.name: p for p in operation.parameters if p.location == "query"} if operation else {}
    )
    pairs = query_pairs(exchange.target)
    owned = _owned_values(exchange, others)
    query: dict[str, IdentifierRef] = {}
    ambiguous: set[str] = set()
    for name, value in pairs:
        parameter = declared.get(name)
        if parameter is None or name in query or name in ambiguous:
            continue
        if not is_identifier_name(name, extra_names) or not _schema_fits(parameter.value_schema):
            continue
        repeated = sum(1 for other, _ in pairs if other == name) > 1
        ref = _query_ref(parameter, value, repeated, owned)
        if ref is None:
            ambiguous.add(name)
        else:
            query[name] = ref
    return IdentifierScan(
        refs=(*path, *(query[name] for name in sorted(query))), ambiguous=tuple(sorted(ambiguous))
    )
