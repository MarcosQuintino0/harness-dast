"""Subconjunto de JSON Schema usado para descrever entradas e saídas de uma API.

O modelo é independente da sintaxe do OpenAPI: o adaptador que lê o documento traduz as
diferenças entre as versões 3.0 e 3.1 (`nullable` x `type: [..., "null"]`, `exclusiveMinimum`
booleano x numérico) para os mesmos campos daqui. Este módulo é puro.

Limites conhecidos do subconjunto: `uniqueItems`, `additionalProperties`, `not`,
`discriminator`, `prefixItems`, `multipleOf` e `minProperties` não são representados.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from harness_dast.domain.errors import ConfigError

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
"""Valor JSON arbitrário (entra e sai das requisições geradas)."""

type JsonScalar = str | int | float | bool | None

SchemaType = Literal["string", "integer", "number", "boolean", "object", "array", "null"]
MAX_STRING = 2000
MAX_ENUM_VALUES = 1000
MAX_PROPERTIES = 500
MAX_BRANCHES = 50


class ApiModel(BaseModel):
    """Base dos modelos de descrição da API: congelados, sem campo extra e sem eco de valor."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class Schema(ApiModel):
    """Esquema de um valor (parâmetro, campo de corpo ou resposta).

    A composição (`one_of`, `any_of`, `all_of`) fica explícita; `flatten_schema` a resolve
    quando é preciso gerar um valor. Um nó `truncated` marca onde o carregador cortou uma
    referência recursiva ou um aninhamento profundo demais: nada se sabe além dele.

    Attributes:
        type: Tipo JSON, ou `None` quando não declarado.
        format: Formato declarado (`date`, `uuid`, `int64`...).
        enum: Valores permitidos, sem `null` (que vira `nullable`).
        minimum: Limite inferior numérico (`exclusive_minimum` diz se ele é aberto).
        maximum: Limite superior numérico.
        min_length: Tamanho mínimo de texto.
        max_length: Tamanho máximo de texto.
        pattern: Expressão regular declarada (nunca executada com `re` sobre o valor).
        min_items: Mínimo de itens de lista.
        max_items: Máximo de itens de lista.
        items: Esquema dos itens de uma lista.
        properties: Campos de um objeto, na ordem declarada.
        required: Nomes dos campos obrigatórios.
        nullable: Se `null` é aceito.
        read_only: Campo só de resposta (não deve ser enviado).
        default: Valor padrão escalar declarado (não é usado para gerar dados).
        example: Exemplo escalar declarado (não é usado para gerar dados).
        one_of: Alternativas exclusivas.
        any_of: Alternativas.
        all_of: Esquemas que valem ao mesmo tempo.
        truncated: O carregador cortou o esquema neste ponto.
    """

    type: SchemaType | None = None
    format: str | None = Field(default=None, max_length=64)
    enum: tuple[JsonScalar, ...] | None = Field(default=None, max_length=MAX_ENUM_VALUES)
    minimum: int | float | None = None
    maximum: int | float | None = None
    exclusive_minimum: bool = False
    exclusive_maximum: bool = False
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(default=None, max_length=MAX_STRING)
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)
    items: "Schema | None" = None
    properties: dict[str, "Schema"] = Field(default_factory=dict, max_length=MAX_PROPERTIES)
    required: tuple[str, ...] = ()
    nullable: bool = False
    read_only: bool = False
    default: JsonScalar = None
    example: JsonScalar = None
    declared_examples: tuple[JsonValue, ...] = Field(default=(), exclude=True, repr=False)
    one_of: tuple["Schema", ...] = Field(default=(), max_length=MAX_BRANCHES)
    any_of: tuple["Schema", ...] = Field(default=(), max_length=MAX_BRANCHES)
    all_of: tuple["Schema", ...] = Field(default=(), max_length=MAX_BRANCHES)
    truncated: bool = False

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        """Recusa intervalos invertidos, que nenhum valor satisfaria."""
        _require_ordered(self.minimum, self.maximum, "minimum maior que maximum")
        _require_ordered(self.min_length, self.max_length, "min_length maior que max_length")
        _require_ordered(self.min_items, self.max_items, "min_items maior que max_items")
        return self


def _require_ordered(low: float | None, high: float | None, message: str) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError(message)


def effective_type(schema: Schema) -> SchemaType | None:
    """Tipo declarado ou, na falta dele, o inferido da estrutura (`properties`, `items`)."""
    if schema.type is not None:
        return schema.type
    if schema.properties:
        return "object"
    if schema.items is not None:
        return "array"
    return None


def split_field_path(path: str) -> tuple[str, ...]:
    """Divide um caminho de campo com pontos (`data.id`, `items.0.id`) em segmentos."""
    return tuple(path.split("."))


def _first_non_null(branches: tuple[Schema, ...]) -> Schema | None:
    for branch in branches:
        if branch.type != "null":
            return branch
    return None


def _intersect_enums(
    first: tuple[JsonScalar, ...] | None, second: tuple[JsonScalar, ...] | None
) -> tuple[JsonScalar, ...] | None:
    if first is None or second is None:
        return first if second is None else second
    return tuple(value for value in first if value in second)


def _tighter[T: float](first: T | None, second: T | None, *, lower: bool) -> T | None:
    if first is None or second is None:
        return first if second is None else second
    return max(first, second) if lower else min(first, second)


def _merge_type(left: SchemaType | None, right: SchemaType | None) -> SchemaType | None:
    if left is None or right is None or left == right:
        return left or right
    if {left, right} == {"integer", "number"}:
        return "integer"
    raise ConfigError(
        "Esquema com tipos incompatíveis ao combinar allOf (por exemplo, texto e inteiro).",
        hint="Corrija o esquema do OpenAPI ou escreva uma regra em data-rules.yml.",
    )


def _merge_text(left: str | None, right: str | None, what: str) -> str | None:
    if left is None or right is None or left == right:
        return left or right
    raise ConfigError(
        f"Esquema com {what} diferentes ao combinar allOf; não há como satisfazer os dois.",
        hint="Corrija o esquema do OpenAPI ou escreva uma regra em data-rules.yml.",
    )


def _merge_pair(left: Schema, right: Schema) -> Schema:
    """Combina dois esquemas sem composição; vale o mais restritivo de cada limite."""
    properties = dict(left.properties)
    for name, sub in right.properties.items():
        properties[name] = Schema(all_of=(properties[name], sub)) if name in properties else sub
    items = left.items
    if left.items is not None and right.items is not None:
        items = Schema(all_of=(left.items, right.items))
    elif right.items is not None:
        items = right.items
    try:
        return _build_merged(left, right, properties, items)
    except ValidationError:
        raise ConfigError(
            "Esquema com restrições contraditórias ao combinar allOf (por exemplo, mínimo "
            "maior que o máximo).",
            hint="Corrija o esquema do OpenAPI ou escreva uma regra em data-rules.yml.",
        ) from None


def _build_merged(
    left: Schema, right: Schema, properties: dict[str, Schema], items: Schema | None
) -> Schema:
    return Schema(
        type=_merge_type(left.type, right.type),
        format=_merge_text(left.format, right.format, "format"),
        enum=_intersect_enums(left.enum, right.enum),
        minimum=_tighter(left.minimum, right.minimum, lower=True),
        maximum=_tighter(left.maximum, right.maximum, lower=False),
        exclusive_minimum=left.exclusive_minimum or right.exclusive_minimum,
        exclusive_maximum=left.exclusive_maximum or right.exclusive_maximum,
        min_length=_tighter(left.min_length, right.min_length, lower=True),
        max_length=_tighter(left.max_length, right.max_length, lower=False),
        pattern=_merge_text(left.pattern, right.pattern, "pattern"),
        min_items=_tighter(left.min_items, right.min_items, lower=True),
        max_items=_tighter(left.max_items, right.max_items, lower=False),
        items=items,
        properties=properties,
        required=tuple(dict.fromkeys((*left.required, *right.required))),
        nullable=left.nullable or right.nullable,
        read_only=left.read_only or right.read_only,
        default=left.default if left.default is not None else right.default,
        example=left.example if left.example is not None else right.example,
        truncated=left.truncated or right.truncated,
    )


def flatten_schema(schema: Schema) -> Schema:
    """Resolve a composição de um esquema, devolvendo um esquema sem `one_of/any_of/all_of`.

    `all_of` é combinado (limites mais restritivos, campos somados). Em `one_of`/`any_of`
    vale a primeira alternativa que não seja `null`: a requisição precisa de UM valor
    válido, não de todos. Só o nível raiz é achatado; propriedades e itens aninhados são
    achatados quando visitados, por isso o resultado não cresce em esquemas grandes.

    Args:
        schema: Esquema possivelmente composto.

    Returns:
        Esquema equivalente para efeito de geração, sem composição no nível raiz.
    """
    base = schema.model_copy(update={"one_of": (), "any_of": (), "all_of": ()})
    merged = base
    for part in schema.all_of:
        merged = _merge_pair(merged, flatten_schema(part))
    alternative = _first_non_null(schema.one_of) or _first_non_null(schema.any_of)
    if alternative is not None:
        merged = _merge_pair(merged, flatten_schema(alternative))
    return merged


def find_property_path(schema: Schema, segments: tuple[str, ...]) -> Schema | None:
    """Segue um caminho de campo (`data.id`, `items.0.id`) e devolve o esquema do destino.

    Um segmento numérico atravessa uma lista (qualquer índice vale: o esquema dos itens é
    um só). Um nó `truncated` no meio do caminho aceita o resto sem conferir, porque o
    carregador não guardou o que há além dele.

    Args:
        schema: Esquema de partida.
        segments: Segmentos do caminho, de `split_field_path`.

    Returns:
        O esquema do campo, ou `None` se o caminho não existe.
    """
    current = schema
    for segment in segments:
        current = flatten_schema(current)
        if current.truncated:
            return current
        if current.items is not None and segment.isdigit():
            current = current.items
        elif segment in current.properties:
            current = current.properties[segment]
        else:
            return None
    return current
