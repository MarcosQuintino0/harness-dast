"""Marcador da escrita em recurso de outra conta: um campo, um valor que difere do atual (ADR 0042).

A verificação `horizontal_write` precisa de um efeito observável: a conta B escreve num campo do
recurso da conta A e a conta A lê de volta. Repetir o corpo do `probe` sem mudança não distingue
"escreveu" de "ignorou" (o estado já seria aquele), então troca-se UM campo escalar de primeiro
nível por um valor que difere do atual: texto ganha o sufixo `-hdast`; inteiro anda um passo.
Nunca recai num campo de segredo, identificador, privilégio, saldo, preço, estado, dono ou de
auditoria. O valor atual vem da leitura anterior da conta dona, e o campo precisa aparecer nela
com o mesmo nome e o mesmo tipo. Determinístico. Este módulo é puro.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.authz.config import normalize_field_name
from harness_dast.domain.authz.fields import AUDIT_NAMES, classify_candidate
from harness_dast.domain.authz.identifiers import ID_WORDS
from harness_dast.domain.authz.sensitive import classify_field_name, field_words

MARKER_SUFFIX: Final = "-hdast"


@dataclass(frozen=True)
class Marker:
    """O campo escolhido e os valores envolvidos (só vivem em memória; nunca são gravados).

    Attributes:
        field: Nome do campo de primeiro nível.
        value: Valor de teste que a conta B escreve.
        previous: Valor atual (da leitura anterior), com o qual a conta dona restaura.
    """

    field: str
    value: str | int
    previous: str | int


def _is_protected(name: str) -> bool:
    """Nome que nunca recebe marcador: segredo, identificador, auditoria ou campo de classe."""
    if classify_field_name(name) == "secret" or normalize_field_name(name) in AUDIT_NAMES:
        return True
    words = field_words(name)
    if words and words[-1] in ID_WORDS:
        return True
    return classify_candidate(name) is not None


def _text_marker(current: str, schema: Schema | None) -> str | None:
    if schema is not None:
        if schema.type not in (None, "string") or schema.enum:
            return None
        if schema.format is not None or schema.pattern is not None:
            return None
    limit = schema.max_length if schema is not None else None
    base = current
    if limit is not None:
        if limit <= len(MARKER_SUFFIX):
            return None
        base = current[: limit - len(MARKER_SUFFIX)]
    marker = base + MARKER_SUFFIX
    return marker if marker != current else None


def _int_marker(current: int, schema: Schema | None) -> int | None:
    if schema is not None and (schema.type not in (None, "integer") or schema.enum):
        return None
    up, down = current + 1, current - 1
    if schema is None:
        return up
    if schema.maximum is None or up <= schema.maximum:
        return up if _fits_minimum(up, schema) else None
    return down if _fits_minimum(down, schema) else None


def _fits_minimum(value: int, schema: Schema) -> bool:
    return schema.minimum is None or value >= schema.minimum


def choose_marker(
    body: Mapping[str, JsonValue],
    before: JsonValue | None,
    properties: Mapping[str, Schema] | None = None,
) -> Marker | None:
    """Escolhe o campo e o valor de teste, ou `None` se nenhum campo serve.

    Texto vem primeiro (na ordem do corpo); só na falta de texto entra inteiro.

    Args:
        body: Corpo JSON (objeto) que o `probe` enviou.
        before: Leitura anterior da conta dona (objeto); sem objeto, não há marcador.
        properties: Esquema de entrada por campo (do OpenAPI), quando declarado.

    Returns:
        O marcador, ou `None` (a operação vai para `no_detectable_field`).
    """
    if not isinstance(before, dict):
        return None
    shapes = properties or {}
    for name, sent in body.items():
        current = before.get(name)
        if isinstance(sent, str) and isinstance(current, str) and not _is_protected(name):
            text = _text_marker(current, shapes.get(name))
            if text is not None:
                return Marker(name, text, current)
    for name, sent in body.items():
        current = before.get(name)
        if type(sent) is int and type(current) is int and not _is_protected(name):
            number = _int_marker(current, shapes.get(name))
            if number is not None:
                return Marker(name, number, current)
    return None
