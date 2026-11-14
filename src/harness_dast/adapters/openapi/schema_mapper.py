"""Tradução de objetos Schema do OpenAPI (3.0 e 3.1) para o `Schema` do domínio.

Resolve `$ref` locais, normaliza as diferenças entre as versões (`nullable` x tipo com
`null`; `exclusiveMinimum` booleano x numérico; `const`) e protege contra documentos
hostis: recursão (corta o ciclo e marca o nó como `truncated`), profundidade e total de nós
expandidos limitados. Nenhum texto do documento vai para mensagens além de identificadores
curtos e saneados.
"""

import datetime as dt
import math
from collections.abc import Mapping
from typing import cast

from harness_dast.adapters.openapi.refs import Raw, RefResolver, escape_pointer
from harness_dast.domain.api_schema import (
    MAX_BRANCHES,
    MAX_ENUM_VALUES,
    MAX_PROPERTIES,
    MAX_STRING,
    JsonScalar,
    JsonValue,
    Schema,
    SchemaType,
)
from harness_dast.domain.errors import ConfigError

MAX_SCHEMA_DEPTH = 24
MAX_SCHEMA_NODES = 200_000
_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "number", "boolean", "object", "array", "null"}
)


def to_scalar(value: Raw) -> JsonScalar:
    """Converte um valor do YAML/JSON em escalar JSON; o que não for escalar vira `None`.

    Datas do YAML (`2020-01-01`) viram texto ISO. Textos acima de 2000 caracteres, números
    não finitos e estruturas são descartados.
    """
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str) and len(value) > MAX_STRING:
        return None
    return value if isinstance(value, str | int | float | bool) else None


class SchemaMapper:
    """Converte esquemas de um documento; guarda só o contador de nós expandidos."""

    def __init__(self, resolver: RefResolver) -> None:
        """Cria o mapeador sobre um resolvedor de referências."""
        self._resolver = resolver
        self._nodes = 0

    def convert(self, node: Raw, where: str, depth: int = 0, stack: tuple[str, ...] = ()) -> Schema:
        """Converte um objeto Schema (ou `true`/`false` do 3.1, que viram "qualquer valor").

        Args:
            node: Objeto lido do documento.
            where: Localização (ponteiro) para as mensagens.
            depth: Profundidade atual.
            stack: Referências em expansão, para cortar ciclos.

        Raises:
            ConfigError: Estrutura inválida (com localização), referência não suportada ou
                documento que expande além do limite de nós.
        """
        self._nodes += 1
        if self._nodes > MAX_SCHEMA_NODES:
            raise ConfigError(
                f"O OpenAPI expande para mais de {MAX_SCHEMA_NODES} esquemas (referências "
                "reutilizadas em excesso).",
                hint="Simplifique os esquemas ou reduza o reuso de referências.",
            )
        if isinstance(node, bool) or node is None:
            return Schema()
        if not isinstance(node, Mapping):
            raise ConfigError(f"{where}: o esquema deve ser um objeto.")
        if "$ref" in node:
            return self._convert_ref(node["$ref"], where, depth, stack)
        if depth > MAX_SCHEMA_DEPTH:
            return Schema(truncated=True)
        return self._build(node, where, depth, stack)

    def _convert_ref(self, ref: Raw, where: str, depth: int, stack: tuple[str, ...]) -> Schema:
        canonical, target = self._resolver.resolve(ref, where)
        if canonical in stack:
            return Schema(truncated=True)
        return self.convert(target, canonical, depth, (*stack, canonical))

    def _build(
        self, node: Mapping[str, Raw], where: str, depth: int, stack: tuple[str, ...]
    ) -> Schema:
        schema_type, nullable = _type_info(node, where)
        enum, enum_null = _enum(node, where)
        minimum, exclusive_minimum = _bound(node, "minimum", "exclusiveMinimum", where)
        maximum, exclusive_maximum = _bound(node, "maximum", "exclusiveMaximum", where)
        return Schema(
            type=schema_type,
            format=_opt_str(node, "format", where, 64),
            enum=enum,
            enum_allows_null=enum_null,
            nullable=nullable or enum_null or node.get("nullable") is True,
            read_only=node.get("readOnly") is True,
            pattern=_opt_str(node, "pattern", where, MAX_STRING, drop_long=True),
            default=to_scalar(node.get("default")),
            example=to_scalar(node.get("example")),
            declared_examples=read_schema_examples(node),
            min_length=_opt_int(node, "minLength", where),
            max_length=_opt_int(node, "maxLength", where),
            min_items=_opt_int(node, "minItems", where),
            max_items=_opt_int(node, "maxItems", where),
            minimum=minimum,
            maximum=maximum,
            exclusive_minimum=exclusive_minimum,
            exclusive_maximum=exclusive_maximum,
            items=self._items(node, where, depth, stack),
            properties=self._properties(node, where, depth, stack),
            required=_required(node, where),
            one_of=self._branches(node, "oneOf", where, depth, stack),
            any_of=self._branches(node, "anyOf", where, depth, stack),
            all_of=self._branches(node, "allOf", where, depth, stack),
        )

    def _items(
        self, node: Mapping[str, Raw], where: str, depth: int, stack: tuple[str, ...]
    ) -> Schema | None:
        items = node.get("items")
        if items is None or isinstance(items, list):
            return None
        return self.convert(items, f"{where}/items", depth + 1, stack)

    def _properties(
        self, node: Mapping[str, Raw], where: str, depth: int, stack: tuple[str, ...]
    ) -> dict[str, Schema]:
        raw = node.get("properties")
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{where}/properties: deve ser um objeto.")
        if len(raw) > MAX_PROPERTIES:
            raise ConfigError(f"{where}/properties: mais de {MAX_PROPERTIES} campos.")
        return {
            str(name): self.convert(
                sub, f"{where}/properties/{escape_pointer(str(name))}", depth + 1, stack
            )
            for name, sub in raw.items()
        }

    def _branches(
        self, node: Mapping[str, Raw], key: str, where: str, depth: int, stack: tuple[str, ...]
    ) -> tuple[Schema, ...]:
        raw = node.get(key)
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ConfigError(f"{where}/{key}: deve ser uma lista.")
        if len(raw) > MAX_BRANCHES:
            raise ConfigError(f"{where}/{key}: mais de {MAX_BRANCHES} alternativas.")
        return tuple(
            self.convert(sub, f"{where}/{key}/{index}", depth + 1, stack)
            for index, sub in enumerate(raw)
        )


def _type_info(node: Mapping[str, Raw], where: str) -> tuple[SchemaType | None, bool]:
    raw = node.get("type")
    if raw is None:
        return None, False
    names = raw if isinstance(raw, list) else [raw]
    if not all(isinstance(name, str) and name in _TYPES for name in names):
        raise ConfigError(f"{where}/type: tipo desconhecido ou fora do padrão OpenAPI 3.")
    real = [name for name in names if name != "null"]
    chosen = real[0] if real else "null"
    # `_TYPES` acima já garantiu que `chosen` é um dos valores de SchemaType.
    return cast(SchemaType, chosen), "null" in names and bool(real)


def _enum(node: Mapping[str, Raw], where: str) -> tuple[tuple[JsonScalar, ...] | None, bool]:
    raw = node.get("enum")
    if raw is None and "const" in node:
        raw = [node["const"]]
    if raw is None:
        return None, False
    if not isinstance(raw, list):
        raise ConfigError(f"{where}/enum: deve ser uma lista.")
    if len(raw) > MAX_ENUM_VALUES:
        raise ConfigError(f"{where}/enum: mais de {MAX_ENUM_VALUES} valores.")
    values = tuple(value for value in map(to_scalar, raw) if value is not None)
    return values, any(item is None for item in raw)


def _required(node: Mapping[str, Raw], where: str) -> tuple[str, ...]:
    raw = node.get("required")
    if raw is None or isinstance(raw, bool):
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{where}/required: deve ser uma lista de nomes.")
    return tuple(dict.fromkeys(str(name) for name in raw if isinstance(name, str | int)))


def _opt_str(
    node: Mapping[str, Raw], key: str, where: str, limit: int, *, drop_long: bool = False
) -> str | None:
    raw = node.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ConfigError(f"{where}/{key}: deve ser um texto.")
    if len(raw) > limit:
        if drop_long:
            return None
        raise ConfigError(f"{where}/{key}: texto longo demais.")
    return raw


def _number(node: Mapping[str, Raw], key: str, where: str) -> int | float | None:
    raw = node.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        raise ConfigError(f"{where}/{key}: deve ser um número.")
    return raw


def _opt_int(node: Mapping[str, Raw], key: str, where: str) -> int | None:
    number = _number(node, key, where)
    if number is None:
        return None
    if number < 0 or number != int(number):
        raise ConfigError(f"{where}/{key}: deve ser um inteiro não negativo.")
    return int(number)


def _bound(
    node: Mapping[str, Raw], key: str, exclusive_key: str, where: str
) -> tuple[int | float | None, bool]:
    """Normaliza um limite e os dois estilos de `exclusive*` (3.0 booleano, 3.1 numérico)."""
    value = _number(node, key, where)
    exclusive = node.get(exclusive_key)
    if isinstance(exclusive, int | float) and not isinstance(exclusive, bool):
        return exclusive, True
    return value, exclusive is True


def _json_example(value: Raw, depth: int = 0, budget: list[int] | None = None) -> JsonValue:
    if budget is None:
        budget = [1000]
    budget[0] -= 1
    if depth > 20 or budget[0] < 0:
        raise ValueError("exemplo profundo demais")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list) and len(value) <= 1000:
        return [_json_example(item, depth + 1, budget) for item in value]
    if isinstance(value, Mapping) and len(value) <= 1000 and all(isinstance(k, str) for k in value):
        return {str(k): _json_example(v, depth + 1, budget) for k, v in value.items()}
    raise ValueError("exemplo não JSON ou grande demais")


def read_schema_examples(node: Mapping[str, Raw]) -> tuple[JsonValue, ...]:
    """Preserva exemplos JSON locais; descarta valores incompatíveis ou excessivos."""
    raw: list[Raw] = []
    if "example" in node:
        raw.append(node["example"])
    examples = node.get("examples")
    if isinstance(examples, list):
        raw.extend(examples[:100])
    result: list[JsonValue] = []
    for item in raw:
        try:
            result.append(_json_example(item))
        except ValueError:
            continue
    return tuple(result)
