"""Montagem de UMA requisição válida por operação, a partir do esquema e das regras.

Para cada campo, na ordem: (1) valor encadeado de `flows.yml`; (2) regra de `data-rules.yml`
(a mais específica); (3) primeiro valor do `enum`; (4) valor implícito pelo tipo e formato
do esquema. Todo valor de gerador vem de um `ValueSource` injetado (aleatoriedade e relógio
moram no adaptador, nunca aqui), e TODO valor é conferido contra o esquema antes de entrar na
requisição. Exemplos e padrões (`example`, `default`) do OpenAPI não são usados: repetem
valores e causam HTTP 409.

Escolhas determinísticas, sem sorteio: `oneOf`/`anyOf` usam a primeira alternativa que não
seja `null`; listas têm `max(minItems, 1)` itens; campos opcionais são enviados quando se
sabe gerá-los; campos `readOnly` nunca são enviados. Este módulo é puro.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from urllib.parse import quote

from pydantic import Field

from harness_dast.domain.api_model import Operation, Parameter, safe_identifier
from harness_dast.domain.api_schema import (
    ApiModel,
    JsonValue,
    Schema,
    effective_type,
    flatten_schema,
)
from harness_dast.domain.datagen import DataRules, ResolvedRule, RuleLocation
from harness_dast.domain.datagen_catalog import get_generator, validate_args
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.flow import BoundValue, ResolvedBindings
from harness_dast.domain.implicit_values import FieldNotGeneratable, implicit_draw
from harness_dast.domain.multipart_encoding import MULTIPART_MEDIA_TYPE
from harness_dast.domain.multipart_schema import PartPlan, plan_parts
from harness_dast.domain.routing_headers import is_routing_header
from harness_dast.domain.schema_check import violations
from harness_dast.domain.synthetic_files import (
    DEFAULT_KIND,
    FileSpec,
    default_filename,
    parse_file_spec,
)
from harness_dast.domain.unique_values import MAX_UNIQUE_TOKENS, validate_run_tag

MAX_BUILD_DEPTH = 12
MAX_ITEMS = 20
_SKIPPED_HEADERS = frozenset({"authorization", "content-type", "accept", "cookie"})
_LOCATIONS: tuple[RuleLocation, ...] = ("path", "query", "header", "cookie")
_RULE_HINT = "Escreva uma regra em data-rules.yml para este campo."


class ValueRequest(ApiModel):
    """Pedido de um valor a um gerador (o contrato entre o domínio e o adaptador).

    Attributes:
        generator: Nome do gerador do catálogo.
        args: Argumentos validados, com os padrões já aplicados.
        value_schema: Esquema (achatado) do campo, para o gerador respeitar limites.
        field_path: Caminho legível do campo (`body.itens[0].cpf`), só para mensagens.
        field_name: Nome do campo (último segmento).
        location: `path`, `query`, `header`, `cookie` ou `body`.
        operation_id: Operação que está sendo montada.
        unique: Se o valor precisa ser único na execução.
        counter: Contador único da execução (0 quando `unique` é falso).
        draw_index: Quantas vezes esta regra já foi usada na montagem (começa em 0).
        run_tag: Etiqueta da execução (ver `unique_values`).
    """

    generator: str
    args: dict[str, JsonValue]
    value_schema: Schema
    field_path: str
    field_name: str
    location: RuleLocation
    operation_id: str
    unique: bool
    counter: int = Field(ge=0)
    draw_index: int = Field(ge=0)
    run_tag: str


ValueSource = Callable[[ValueRequest], JsonValue]
"""Porta de valores: recebe o pedido e devolve um valor JSON. Implementada em adapters."""


class BuiltRequest(ApiModel):
    """Requisição concreta, pronta para o cliente HTTP (o escopo é decidido por quem a envia).

    Attributes:
        operation_id: Operação de origem.
        method: Método HTTP em maiúsculas.
        path: Caminho com os parâmetros de caminho preenchidos e codificados.
        query: Pares (nome, valor) da query, na ordem de geração.
        headers: Cabeçalhos de parâmetros (sem Authorization, Content-Type nem Accept).
        cookies: Cookies de parâmetros.
        body: Corpo como valor JSON (também para mídias não JSON; quem envia codifica).
        body_media_type: Tipo de mídia do corpo, ou `None` se não há corpo.
        files: Campos de arquivo sintético (só `multipart/form-data`); `body` leva os campos de
            texto.
        skipped_fields: Campos opcionais omitidos por não terem gerador possível.
    """

    operation_id: str
    method: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None
    body_media_type: str | None = None
    files: tuple[FileSpec, ...] = ()
    skipped_fields: tuple[str, ...] = ()


class _Omitted:
    """Marca de campo opcional pulado (não é um valor JSON)."""


_OMIT = _Omitted()


@dataclass(frozen=True)
class _Ctx:
    operation_id: str
    location: RuleLocation
    segments: tuple[str, ...]
    display: str
    depth: int
    skipped: list[str]
    bound: ResolvedBindings

    def child(self, name: str) -> "_Ctx":
        return replace(
            self,
            segments=(*self.segments, name),
            display=f"{self.display}.{name}",
            depth=self.depth + 1,
        )

    def item(self, index: int) -> "_Ctx":
        return replace(self, display=f"{self.display}[{index}]", depth=self.depth + 1)


def _stringify(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _coerce(value: JsonValue, schema_type: str | None) -> JsonValue:
    """Ajusta o tipo de um valor de gerador ao do campo (texto numérico <-> número)."""
    if isinstance(value, bool):
        return value
    if schema_type in {"integer", "number"} and isinstance(value, str):
        text = value.lstrip("-")
        return int(value) if text.isascii() and text.isdigit() else value
    if schema_type == "string" and isinstance(value, int | float):
        return str(value)
    return value


class RequestBuilder:
    """Monta requisições válidas; guarda só o estado da execução (contadores e únicos usados).

    Uma instância vale por uma execução: o contador de únicos nunca volta atrás, então dois
    valores `unique` da mesma instância nunca coincidem.
    """

    def __init__(self, rules: DataRules, source: ValueSource, run_tag: str) -> None:
        """Cria o montador.

        Args:
            rules: Regras de dados já validadas.
            source: Fonte de valores (catálogo de geradores com semente e relógio injetados).
            run_tag: Etiqueta da execução, de `run_tag_from_run_id`.

        Raises:
            ConfigError: Etiqueta inválida.
        """
        self._rules = rules
        self._source = source
        self._run_tag = validate_run_tag(run_tag)
        self._unique_counter = 0
        self._draws: dict[str, int] = {}
        self._seen: dict[int, set[str]] = {}

    def build(self, operation: Operation, bindings: ResolvedBindings | None = None) -> BuiltRequest:
        """Monta a requisição da operação.

        Args:
            operation: A operação.
            bindings: Valores encadeados das respostas dos produtores, se houver.

        Returns:
            A requisição concreta.

        Raises:
            ConfigError: Campo obrigatório sem como gerar valor (a dica pede uma regra),
                valor de regra que viola o esquema, valor único repetido ou esgotado.
        """
        bound = bindings or ResolvedBindings()
        skipped: list[str] = []
        values = {
            location: self._parameters(operation, location, bound, skipped)
            for location in _LOCATIONS
        }
        media_type, body, files = self._body(operation, bound, skipped)
        return BuiltRequest(
            operation_id=operation.operation_id,
            method=operation.method.upper(),
            path=self._render_path(operation, dict(values["path"])),
            query=tuple(self._query_pairs(values["query"])),
            headers={name: _stringify(value) for name, value in values["header"]},
            cookies={name: _stringify(value) for name, value in values["cookie"]},
            body=body,
            body_media_type=media_type,
            files=files,
            skipped_fields=tuple(skipped),
        )

    def _parameters(
        self,
        operation: Operation,
        location: RuleLocation,
        bound: ResolvedBindings,
        skipped: list[str],
    ) -> list[tuple[str, JsonValue]]:
        result: list[tuple[str, JsonValue]] = []
        for parameter in self._declared(operation, location):
            if location == "header" and parameter.name.lower() in _SKIPPED_HEADERS:
                continue
            if location == "header" and is_routing_header(parameter.name):
                skipped.append(f"header.{parameter.name} (cabeçalho de roteamento: nunca enviado)")
                continue
            ctx = _Ctx(
                operation.operation_id,
                location,
                (parameter.name,),
                f"{location}.{parameter.name}",
                0,
                skipped,
                bound,
            )
            value = self._parameter_value(parameter, ctx)
            if not isinstance(value, _Omitted):
                result.append((parameter.name, value))
        return result

    @staticmethod
    def _declared(operation: Operation, location: RuleLocation) -> list[Parameter]:
        declared = [p for p in operation.parameters if p.location == location]
        if location != "path":
            return declared
        known = {p.name for p in declared}
        # O documento pode esquecer de declarar um `{marcador}` do caminho; sem valor a
        # requisição não existiria, então ele vira um parâmetro de texto.
        undeclared = [
            Parameter(name=name, location="path", required=True, value_schema=Schema(type="string"))
            for name in operation.path_placeholders
            if name not in known
        ]
        return declared + undeclared

    def _parameter_value(self, parameter: Parameter, ctx: _Ctx) -> JsonValue | _Omitted:
        if parameter.name in ctx.bound.params:
            return self._bound(ctx.bound.params[parameter.name], parameter.value_schema)
        if parameter.required:
            return self._make(parameter.value_schema, ctx)
        return self._make_optional(parameter.value_schema, ctx)

    def _body(
        self, operation: Operation, bound: ResolvedBindings, skipped: list[str]
    ) -> tuple[str | None, JsonValue, tuple[FileSpec, ...]]:
        media = operation.request_body.preferred() if operation.request_body else None
        if media is None:
            return None, None, ()
        ctx = _Ctx(operation.operation_id, "body", (), "body", 0, skipped, bound)
        if media.media_type.split(";")[0].strip().lower() == MULTIPART_MEDIA_TYPE:
            fields, files = self._multipart(media.body_schema, media.part_content_types, ctx)
            return media.media_type, fields, files
        if media.body_schema is None:
            return media.media_type, None, ()
        return media.media_type, self._make(media.body_schema, ctx), ()

    def _multipart(
        self, schema: Schema | None, part_types: Mapping[str, str], ctx: _Ctx
    ) -> tuple[JsonValue, tuple[FileSpec, ...]]:
        """Campos de texto (pelo caminho de sempre) e arquivos sintéticos do corpo multipart."""
        fields: dict[str, JsonValue] = {}
        files: list[FileSpec] = []
        for plan in plan_parts(schema, part_types):
            child = ctx.child(plan.name)
            if plan.is_file:
                files.append(self._file_spec(plan, child))
                continue
            value = (
                self._make(plan.schema, child)
                if plan.required
                else self._make_optional(plan.schema, child)
            )
            if not isinstance(value, _Omitted):
                fields[plan.name] = value
        return fields, tuple(files)

    def _file_spec(self, plan: PartPlan, ctx: _Ctx) -> FileSpec:
        """Tipo e nome do arquivo: padrão, `encoding.contentType` ou regra `synthetic_file`."""
        if plan.unsupported_declared is not None:
            ctx.skipped.append(
                f"{ctx.display} (tipo declarado {safe_identifier(plan.unsupported_declared)} sem "
                "arquivo sintético: enviado como text/plain)"
            )
        resolved = self._rules.resolve(ctx.operation_id, "body", ctx.segments)
        if resolved is None:
            kind = plan.declared_kind or DEFAULT_KIND
            return FileSpec(field=plan.name, kind=kind, filename=default_filename(kind))
        rule = resolved.rule
        if rule.generator != "synthetic_file":
            raise ConfigError(
                f"A regra {resolved.index + 1} de data-rules.yml cobre o campo de arquivo "
                f"{safe_identifier(plan.name)}, mas o gerador não é synthetic_file.",
                hint="Para campo de arquivo use generator: synthetic_file (kind e name em args).",
            )
        text = self._draw(
            rule.generator, rule.args, plan.schema, ctx, resolved=resolved, unique=False
        )
        if not isinstance(text, str):
            raise ConfigError(
                "O gerador synthetic_file devolveu algo que não é texto.", hint="Erro interno."
            )
        kind, filename = parse_file_spec(text)
        return FileSpec(field=plan.name, kind=kind, filename=filename)

    @staticmethod
    def _render_path(operation: Operation, values: dict[str, JsonValue]) -> str:
        path = operation.path
        for name in operation.path_placeholders:
            path = path.replace("{" + name + "}", quote(_stringify(values[name]), safe=""))
        return path

    @staticmethod
    def _query_pairs(values: list[tuple[str, JsonValue]]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for name, value in values:
            items = value if isinstance(value, list) else [value]
            pairs.extend((name, _stringify(item)) for item in items)
        return pairs

    @staticmethod
    def _bound(value: BoundValue, schema: Schema) -> JsonValue:
        flat = flatten_schema(schema)
        schema_type = effective_type(flat)
        fitted = _coerce(value, schema_type)
        problems = violations(flat, fitted) if schema_type else ()
        if problems:
            raise ConfigError(
                "Um valor encadeado de flows.yml não atende ao esquema do destino "
                f"({', '.join(problems)}).",
                hint="Confira se produtor e consumidor falam do mesmo identificador.",
            )
        return fitted

    def _make_optional(self, schema: Schema, ctx: _Ctx) -> JsonValue | _Omitted:
        """Como `_make`, mas pula o campo (e o registra) se não souber gerá-lo."""
        try:
            return self._make(schema, ctx)
        except FieldNotGeneratable:
            ctx.skipped.append(ctx.display)
            return _OMIT

    def _make(self, schema: Schema, ctx: _Ctx) -> JsonValue:
        flat = flatten_schema(schema)
        key = ".".join(ctx.segments)
        if ctx.location == "body" and key in ctx.bound.fields:
            return self._bound(ctx.bound.fields[key], flat)
        if ctx.depth > MAX_BUILD_DEPTH:
            raise FieldNotGeneratable(
                f"O campo {safe_identifier(ctx.display)} é aninhado demais para gerar.",
                hint=_RULE_HINT,
            )
        schema_type = effective_type(flat)
        if schema_type == "object" or (flat.truncated and schema_type is None):
            return self._make_object(flat, ctx)
        if schema_type == "array":
            return self._make_array(flat, ctx)
        return self._make_leaf(flat, ctx, schema_type)

    def _make_object(self, flat: Schema, ctx: _Ctx) -> JsonValue:
        result: dict[str, JsonValue] = {}
        for name, sub in flat.properties.items():
            flat_sub = flatten_schema(sub)
            if flat_sub.read_only or (flat_sub.truncated and name not in flat.required):
                continue
            child = ctx.child(name)
            value = (
                self._make(sub, child) if name in flat.required else self._make_optional(sub, child)
            )
            if not isinstance(value, _Omitted):
                result[name] = value
        return result

    def _make_array(self, flat: Schema, ctx: _Ctx) -> JsonValue:
        minimum = flat.min_items or 0
        item_schema = flat.items
        if item_schema is None or item_schema.truncated:
            count = 0
        else:
            count = max(minimum, 1)
            if flat.max_items is not None:
                count = min(count, flat.max_items)
        if count < minimum or count > MAX_ITEMS:
            raise FieldNotGeneratable(
                f"Não é possível montar a lista {safe_identifier(ctx.display)} com o mínimo "
                "de itens exigido.",
                hint=_RULE_HINT,
            )
        if item_schema is None:
            return []
        return [self._make(item_schema, ctx.item(index)) for index in range(count)]

    def _make_leaf(self, flat: Schema, ctx: _Ctx, schema_type: str | None) -> JsonValue:
        if schema_type == "null":
            return None
        resolved = self._rules.resolve(ctx.operation_id, ctx.location, ctx.segments)
        if resolved is not None:
            rule = resolved.rule
            value = self._draw(
                rule.generator, rule.args, flat, ctx, resolved=resolved, unique=rule.unique
            )
        elif flat.enum:
            value = next((option for option in flat.enum if option is not None), None)
        else:
            generator, args = implicit_draw(flat, schema_type, ctx.display)
            value = self._draw(generator, args, flat, ctx, resolved=None, unique=False)
        value = _coerce(value, schema_type)
        problems = violations(flat, value) if schema_type is not None else ()
        if problems:
            self._fail_invalid_value(problems, ctx, resolved)
        return value

    @staticmethod
    def _fail_invalid_value(
        problems: tuple[str, ...], ctx: _Ctx, resolved: ResolvedRule | None
    ) -> None:
        detail = (
            f"O valor gerado para {safe_identifier(ctx.display)} não atende ao esquema: "
            f"{', '.join(problems)}."
        )
        if resolved is None:
            raise FieldNotGeneratable(detail, hint=_RULE_HINT)
        raise ConfigError(
            detail, hint=f"Ajuste a regra {resolved.index + 1} de data-rules.yml (gerador ou args)."
        )

    def _draw(
        self,
        generator: str,
        raw_args: Mapping[str, object],
        flat: Schema,
        ctx: _Ctx,
        *,
        resolved: ResolvedRule | None,
        unique: bool,
    ) -> JsonValue:
        args = validate_args(get_generator(generator), raw_args)
        draw_key = f"r{resolved.index}" if resolved else f"i:{generator}"
        draw_index = self._draws.get(draw_key, 0)
        self._draws[draw_key] = draw_index + 1
        value = self._source(
            ValueRequest(
                generator=generator,
                args=args,
                value_schema=flat,
                field_path=ctx.display,
                field_name=ctx.segments[-1] if ctx.segments else "body",
                location=ctx.location,
                operation_id=ctx.operation_id,
                unique=unique,
                counter=self._next_counter() if unique else 0,
                draw_index=draw_index,
                run_tag=self._run_tag,
            )
        )
        if unique:
            self._remember_unique(resolved.index if resolved else -1, value, ctx)
        return value

    def _next_counter(self) -> int:
        counter = self._unique_counter
        if counter >= MAX_UNIQUE_TOKENS:
            raise ConfigError(
                "Foram pedidos valores únicos demais nesta execução.",
                hint="Divida o teste em execuções menores.",
            )
        self._unique_counter += 1
        return counter

    def _remember_unique(self, rule_index: int, value: JsonValue, ctx: _Ctx) -> None:
        seen = self._seen.setdefault(rule_index, set())
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if canonical in seen:
            raise ConfigError(
                f"O gerador repetiu um valor único em {safe_identifier(ctx.display)}.",
                hint="Use um gerador que aceite unique (numeric, alphanumeric, email, br.cpf...).",
            )
        seen.add(canonical)
