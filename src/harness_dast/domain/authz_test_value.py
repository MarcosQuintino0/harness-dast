"""Valor de teste de um candidato da atribuição em massa, pelo tipo e pelo valor atual (ADR 0040).

Determinístico, sem aleatoriedade e nunca numa direção que tranque a conta: booleano de
privilégio ou estado bom sobe, estado ruim (`blocked`) desce, número anda um passo na direção do
nome dentro de `minimum`/`maximum`, texto com `enum` usa o primeiro valor diferente do atual (sem
valores de bloqueio em `state`), texto livre usa `admin` (privilégio) ou `hdast-teste`. Sem valor
seguro, o candidato é pulado com um motivo estável. Este módulo é puro.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.api_schema import JsonValue, Schema, effective_type
from harness_dast.domain.authz_candidates import Candidate
from harness_dast.domain.authz_fields import ADMIN_ENUM_PREFERENCE, BAD_STATE_WORDS, moves_up
from harness_dast.domain.authz_sensitive import field_words

SKIP_NO_SAFE_VALUE: Final = "no_safe_test_value"
SKIP_ALREADY_THERE: Final = "already_in_target_state"
TEST_TEXT: Final = "hdast-teste"
_BAD_ENUM_WORDS: Final = BAD_STATE_WORDS | {"inactive", "inativo"}


@dataclass(frozen=True)
class ValuePick:
    """Valor de teste escolhido, ou o motivo de pular o candidato.

    Attributes:
        value: Valor de teste (`None` quando `skip` está preenchido).
        skip: Motivo estável (`no_safe_test_value`, `already_in_target_state`) ou `None`.
    """

    value: JsonValue = None
    skip: str | None = None


def pick_test_value(candidate: Candidate, current: JsonValue = None) -> ValuePick:
    """Valor de teste do candidato, pelo tipo e pelo valor atual (`None` = não lido).

    Determinístico e sem aleatoriedade. O valor declarado vale como está.
    """
    if candidate.source == "declared":
        return ValuePick(candidate.declared_value)
    schema = candidate.schema
    if schema is None:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    kind = effective_type(schema)
    if kind == "boolean":
        return _pick_bool(candidate, current)
    if kind in {"integer", "number"}:
        return _pick_number(candidate, schema, current)
    if kind == "string":
        return _pick_text(candidate, schema, current)
    return ValuePick(skip=SKIP_NO_SAFE_VALUE)


def _same(left: JsonValue, right: JsonValue) -> bool:
    return type(left) is type(right) and left == right


def _pick_bool(candidate: Candidate, current: JsonValue) -> ValuePick:
    if candidate.kind not in {"privilege", "state"}:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    target = moves_up(candidate.name)
    return ValuePick(skip=SKIP_ALREADY_THERE) if _same(current, target) else ValuePick(target)


def _pick_number(candidate: Candidate, schema: Schema, current: JsonValue) -> ValuePick:
    if candidate.kind not in {"privilege", "balance", "price"}:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    integer = effective_type(schema) == "integer"
    seen = current if isinstance(current, int | float) and not isinstance(current, bool) else None
    if integer and isinstance(seen, float):
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    wanted = 1 if seen is None else seen + (1 if moves_up(candidate.name) else -1)
    low, high = _bounds(schema, integer=integer)
    if low is not None and high is not None and low > high:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    if low is not None:
        wanted = max(wanted, low)
    if high is not None:
        wanted = min(wanted, high)
    if seen is not None and wanted == seen:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    return ValuePick(wanted)


def _bounds(schema: Schema, *, integer: bool) -> tuple[int | float | None, int | float | None]:
    """Limites inclusivos do valor: o limite aberto recua para o inteiro seguinte, para dentro."""
    low, high = schema.minimum, schema.maximum
    if low is not None:
        low = (
            math.floor(low) + 1 if schema.exclusive_minimum else _round_in(low, math.ceil, integer)
        )
    if high is not None:
        high = (
            math.ceil(high) - 1
            if schema.exclusive_maximum
            else _round_in(high, math.floor, integer)
        )
    return low, high


def _round_in(value: float, rounding: Callable[[float], int], integer: bool) -> int | float:
    return rounding(value) if integer else value


def _pick_text(candidate: Candidate, schema: Schema, current: JsonValue) -> ValuePick:
    if schema.enum is not None:
        return _pick_enum(candidate, schema.enum, current)
    if schema.format is not None or schema.pattern is not None:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    text = "admin" if candidate.kind == "privilege" else TEST_TEXT
    if candidate.kind != "privilege" and schema.max_length is not None:
        text = text[: schema.max_length]
    if not text or len(text) < (schema.min_length or 0):
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    if schema.max_length is not None and len(text) > schema.max_length:
        return ValuePick(skip=SKIP_NO_SAFE_VALUE)
    return ValuePick(skip=SKIP_ALREADY_THERE) if _same(current, text) else ValuePick(text)


def _pick_enum(
    candidate: Candidate, values: tuple[JsonValue, ...], current: JsonValue
) -> ValuePick:
    texts = [item for item in values if isinstance(item, str) and not _same(item, current)]
    if candidate.kind == "state":
        texts = [item for item in texts if not set(field_words(item)) & _BAD_ENUM_WORDS]
    if candidate.kind == "privilege":
        for preferred in ADMIN_ENUM_PREFERENCE:
            for item in texts:
                if item.lower() == preferred:
                    return ValuePick(item)
    return ValuePick(texts[0]) if texts else ValuePick(skip=SKIP_NO_SAFE_VALUE)
