"""Valores que o esquema proíbe: a escolha, por classe, do que o teste negativo envia (ADR 0051).

Cada classe produz UM valor mínimo, inofensivo e determinístico (ASCII curto, sem aspas, `<`,
`%`, barra nem `..`: isto não é teste de injeção). Antes de existir como caso, o valor é
CONFERIDO por `check_schema` (ADR 0047): o único código devolvido precisa ser o da classe. Se não
for (esquema que o ADR 0047 não modela, tipo `null`, `enum` junto de limite), a classe vira
`unconfirmable` e nada é enviado. Nunca se manda um valor que o próprio domínio não consegue
dizer que é proibido. Este módulo é puro.
"""

import math
from dataclasses import dataclass, field
from typing import Final, Literal

from harness_dast.domain.api_schema import JsonScalar, JsonValue, Schema
from harness_dast.domain.schema_check import check_schema

CaseClass = Literal[
    "wrong_type",
    "missing_required",
    "below_minimum",
    "above_maximum",
    "not_in_enum",
    "too_long",
    "too_short",
]
CLASS_ORDER: Final[tuple[CaseClass, ...]] = (
    "wrong_type",
    "missing_required",
    "below_minimum",
    "above_maximum",
    "not_in_enum",
    "too_long",
    "too_short",
)
"""Prioridade de escolha: a primeira classe aplicável de cada campo vai primeiro."""

MAX_VALUE_CHARS: Final = 1_000
WRONG_NUMBER_TEXT: Final = "not-a-number"
WRONG_BOOLEAN_TEXT: Final = "not-a-boolean"
WRONG_TEXT_NUMBER: Final = 12345
NOT_IN_ENUM_TEXT: Final = "not-in-enum"
_EXPECTED_CODE: Final[dict[CaseClass, str]] = {
    "wrong_type": "type",
    "missing_required": "required",
    "below_minimum": "range",
    "above_maximum": "range",
    "not_in_enum": "enum",
    "too_long": "length",
    "too_short": "length",
}
_NUMBER_TYPES: Final = frozenset({"integer", "number"})
Applicability = Literal["not_applicable", "unconfirmable"]


@dataclass(frozen=True)
class Proposal:
    """O valor proibido de uma classe para um campo.

    Attributes:
        case_class: Classe do caso.
        value: Valor a enviar. Fica fora do `repr` para nunca chegar a log nem a mensagem.
        remove: O campo é REMOVIDO em vez de receber `value` (`missing_required`).
        declared: O limite que o OpenAPI declara (`minimum 1`, `maxLength 50`); vem do contrato.
    """

    case_class: CaseClass
    value: JsonValue = field(repr=False)
    remove: bool
    declared: str


def expected_code(case_class: CaseClass) -> str:
    """Código de `check_schema` que a classe precisa provocar."""
    return _EXPECTED_CODE[case_class]


def _bounded(schema: Schema, value: float) -> JsonValue:
    """Limite deslocado; inteiro Python quando o esquema é `integer` (senão `type` falharia)."""
    if not math.isfinite(value):
        return None
    if schema.type == "integer" and float(value).is_integer():
        return int(value)
    return value


def _number_value(schema: Schema, case_class: CaseClass) -> tuple[JsonValue, str] | None:
    if schema.type not in _NUMBER_TYPES:
        return None
    if case_class == "below_minimum" and schema.minimum is not None:
        step = 0 if schema.exclusive_minimum else -1
        label = "exclusive minimum" if schema.exclusive_minimum else "minimum"
        return _bounded(schema, schema.minimum + step), f"{label} {schema.minimum}"
    if case_class == "above_maximum" and schema.maximum is not None:
        step = 0 if schema.exclusive_maximum else 1
        label = "exclusive maximum" if schema.exclusive_maximum else "maximum"
        return _bounded(schema, schema.maximum + step), f"{label} {schema.maximum}"
    return None


def _wrong_type_value(schema: Schema, *, in_query: bool) -> JsonValue:
    if schema.type in _NUMBER_TYPES:
        return WRONG_NUMBER_TEXT
    if schema.type == "boolean":
        return WRONG_BOOLEAN_TEXT
    if schema.type == "string" and not in_query:
        return WRONG_TEXT_NUMBER
    return None


def _enum_value(options: tuple[JsonScalar, ...]) -> JsonValue:
    if not options:
        return None
    if all(isinstance(item, str) for item in options):
        return NOT_IN_ENUM_TEXT
    numbers = [
        item for item in options if isinstance(item, int | float) and not isinstance(item, bool)
    ]
    if len(numbers) != len(options) or not all(math.isfinite(item) for item in numbers):
        return None
    top = max(numbers) + 1
    return int(top) if all(isinstance(item, int) for item in numbers) else top


def _text_value(schema: Schema, case_class: CaseClass) -> tuple[JsonValue, str] | None:
    if schema.type != "string":
        return None
    if case_class == "too_long" and schema.max_length is not None:
        if schema.max_length + 1 > MAX_VALUE_CHARS:
            return None
        return "a" * (schema.max_length + 1), f"maxLength {schema.max_length}"
    if case_class == "too_short" and schema.min_length:
        if schema.min_length - 1 > MAX_VALUE_CHARS:
            return None
        return "a" * (schema.min_length - 1), f"minLength {schema.min_length}"
    return None


def _raw_value(
    schema: Schema, case_class: CaseClass, *, in_query: bool
) -> tuple[JsonValue, str] | None:
    """Valor candidato e o limite declarado, ou `None` se a classe não se aplica."""
    if case_class in {"below_minimum", "above_maximum"}:
        return _number_value(schema, case_class)
    if case_class in {"too_long", "too_short"}:
        return _text_value(schema, case_class)
    if case_class == "not_in_enum":
        if schema.enum is None:
            return None
        value = _enum_value(schema.enum)
        return (value, f"enum de {len(schema.enum)} valor(es)") if value is not None else None
    if case_class == "wrong_type" and schema.enum is None:
        value = _wrong_type_value(schema, in_query=in_query)
        return (value, f"type {schema.type}") if value is not None else None
    return None


def propose(schema: Schema, case_class: CaseClass, *, in_query: bool) -> Proposal | Applicability:
    """Valor proibido de uma classe para um campo escalar, já conferido por `check_schema`.

    `missing_required` não passa por aqui (veja `propose_missing`). O esquema já deve estar
    achatado.

    Args:
        schema: Esquema do campo.
        case_class: Classe do caso.
        in_query: Se o campo viaja na consulta (todo valor ali já é texto).

    Returns:
        A proposta; `not_applicable` se a classe não cabe no esquema; `unconfirmable` se cabe
        mas `check_schema` não confirma que o valor é proibido pela classe.
    """
    if schema.truncated or schema.read_only or case_class == "missing_required":
        return "not_applicable"
    raw = _raw_value(schema, case_class, in_query=in_query)
    if raw is None:
        return "not_applicable"
    value, declared = raw
    if value is None or len(str(value)) > MAX_VALUE_CHARS:
        return "unconfirmable"
    if check_schema(schema, value) != (expected_code(case_class),):
        return "unconfirmable"
    return Proposal(case_class=case_class, value=value, remove=False, declared=declared)


def propose_missing(
    container: Schema, body: dict[str, JsonValue], name: str
) -> Proposal | Applicability:
    """Remoção de um campo obrigatório, conferida contra o esquema do objeto.

    Args:
        container: Esquema do objeto (achatado) com `required`.
        body: Objeto que o `probe` provou (o campo precisa estar nele).
        name: Campo a remover.
    """
    if name not in container.required or name not in body:
        return "not_applicable"
    reduced = {key: item for key, item in body.items() if key != name}
    if check_schema(container, reduced) != ("required",):
        return "unconfirmable"
    return Proposal(case_class="missing_required", value=None, remove=True, declared="required")
