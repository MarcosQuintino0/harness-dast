"""Quais propriedades de um esquema `multipart/form-data` são arquivo e quais são texto.

Regra do ADR 0052: arquivo é a propriedade `string` com `format: binary` (OpenAPI 3.0), ou a
lista cujos itens são `binary` (vira UM arquivo com o nome do campo). `format: byte` é texto em
base64 e NÃO é arquivo. Campo aninhado, nome de campo fora da regra, esquema ausente ou vazio,
mais de 20 partes e `binary` fora de `string` viram `ConfigError` com a dica do que fazer.
OpenAPI 3.1 (`contentMediaType`) não é modelado. Este módulo é puro.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.api_schema import Schema, effective_type, flatten_schema
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.synthetic_files import (
    MAX_PARTS,
    FileKind,
    is_safe_name,
    kind_from_content_type,
)

_BINARY = "binary"
_HINT = (
    "Declare no OpenAPI um objeto de campos simples (texto) e de arquivos "
    "(`type: string`, `format: binary`), ou deixe a operação fora do plano."
)


@dataclass(frozen=True)
class PartPlan:
    """Uma parte do corpo multipart.

    Attributes:
        name: Nome do campo (já conferido contra a regra de nomes).
        schema: Esquema da propriedade.
        required: Se a propriedade é obrigatória.
        is_file: Se a parte é um arquivo (senão, campo de texto).
        declared_kind: Tipo sintético que o `encoding.contentType` declarado escolhe, ou `None`.
        unsupported_declared: `encoding.contentType` declarado que não tem tipo sintético.
    """

    name: str
    schema: Schema
    required: bool
    is_file: bool
    declared_kind: FileKind | None = None
    unsupported_declared: str | None = None


def _is_file(flat: Schema) -> bool:
    kind = effective_type(flat)
    if kind == "string":
        return flat.format == _BINARY
    if kind == "array" and flat.items is not None:
        item = flatten_schema(flat.items)
        return effective_type(item) == "string" and item.format == _BINARY
    return False


def _refuse(name: str, why: str) -> ConfigError:
    return ConfigError(
        f"multipart_unsupported_schema: o campo {safe_identifier(name)} {why}.", hint=_HINT
    )


def plan_parts(body_schema: Schema | None, part_types: Mapping[str, str]) -> tuple[PartPlan, ...]:
    """Classifica as propriedades do esquema multipart, na ordem declarada.

    Args:
        body_schema: Esquema do corpo `multipart/form-data`.
        part_types: `encoding.<campo>.contentType` declarados no OpenAPI.

    Raises:
        ConfigError: Esquema ausente, vazio ou fora do que o probe monta (ver o docstring do
            módulo).
    """
    if body_schema is None:
        raise ConfigError(
            "multipart_unsupported_schema: o corpo multipart não tem esquema no OpenAPI.",
            hint=_HINT,
        )
    flat = flatten_schema(body_schema)
    plans: list[PartPlan] = []
    for name, sub in flat.properties.items():
        flat_sub = flatten_schema(sub)
        if flat_sub.read_only:
            continue
        required = name in flat.required
        if flat_sub.truncated and not required:
            continue
        if not is_safe_name(name):
            raise _refuse(name, "tem nome fora da regra (ASCII, 1 a 64 caracteres, sem '..')")
        plans.append(_plan(name, flat_sub, required, part_types.get(name)))
    if not plans:
        raise ConfigError(
            "multipart_unsupported_schema: o corpo multipart não declara propriedades.",
            hint=_HINT,
        )
    if len(plans) > MAX_PARTS:
        raise ConfigError(
            f"multipart_unsupported_schema: o corpo tem mais de {MAX_PARTS} partes.", hint=_HINT
        )
    return tuple(plans)


def _plan(name: str, flat: Schema, required: bool, declared: str | None) -> PartPlan:
    kind = effective_type(flat)
    if flat.truncated or kind == "object" or (kind == "array" and not _is_file(flat)):
        raise _refuse(name, "é aninhado (objeto ou lista que não é de arquivos)")
    if flat.format == _BINARY and kind != "string":
        raise _refuse(name, "declara format binary num tipo que não é string")
    if not _is_file(flat):
        return PartPlan(name, flat, required, is_file=False)
    chosen = kind_from_content_type(declared)
    return PartPlan(
        name,
        flat,
        required,
        is_file=True,
        declared_kind=chosen,
        unsupported_declared=declared if declared is not None and chosen is None else None,
    )
