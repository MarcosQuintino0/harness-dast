"""Tradução de caminhos, parâmetros, corpos, respostas e segurança para `Operation`.

Também aplica as regras de identidade: `operationId` declarado repetido é erro; ausente é
sintetizado de forma determinística (com sufixo numérico se colidir com outro).
"""

import re
from collections.abc import Mapping

from pydantic import ValidationError

from harness_dast.adapters.openapi.refs import Raw, RefResolver, escape_pointer
from harness_dast.adapters.openapi.schema_mapper import SchemaMapper
from harness_dast.domain.api_model import (
    MAX_MEDIA_TYPES,
    HttpMethod,
    MediaBody,
    Operation,
    Parameter,
    ParamLocation,
    RequestBody,
    SecurityRequirement,
    SuccessResponse,
    safe_identifier,
    synthesize_operation_id,
)
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ConfigError

HTTP_METHODS: tuple[HttpMethod, ...] = (
    "get", "put", "post", "delete", "options", "head", "patch", "trace",
)  # fmt: skip
_LOCATIONS: tuple[ParamLocation, ...] = ("path", "query", "header", "cookie")
_MAX_TAGS = 20
_MAX_SUMMARY = 200
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class OperationMapper:
    """Converte os `paths` de um documento em operações, com identificadores únicos."""

    def __init__(
        self,
        resolver: RefResolver,
        schemas: SchemaMapper,
        default_security: tuple[SecurityRequirement, ...],
    ) -> None:
        """Cria o mapeador.

        Args:
            resolver: Resolvedor de referências do documento.
            schemas: Conversor de esquemas (compartilha o contador de nós).
            default_security: Segurança do nível raiz do documento.
        """
        self._resolver = resolver
        self._schemas = schemas
        self._default_security = default_security
        self._used_ids: dict[str, str] = {}

    def map_paths(self, paths: Raw) -> tuple[Operation, ...]:
        """Converte o objeto `paths`.

        Raises:
            ConfigError: Estrutura inválida (com ponteiro), `operationId` duplicado ou
                operação que o domínio recusa.
        """
        if not isinstance(paths, Mapping):
            raise ConfigError("#/paths: deve ser um objeto com os caminhos da API.")
        operations: list[Operation] = []
        for raw_path, raw_item in paths.items():
            path = str(raw_path)
            where = f"#/paths/{escape_pointer(path)}"
            if not path.startswith("/"):
                if path.startswith("x-"):
                    continue
                raise ConfigError(f"{where}: o caminho deve começar com '/'.")
            item = self._object(raw_item, where)
            operations.extend(self._path_item(path, item, where))
        return tuple(operations)

    def _object(self, raw: Raw, where: str) -> Mapping[str, Raw]:
        """Devolve o mapa, seguindo `$ref` se houver."""
        if isinstance(raw, Mapping) and "$ref" in raw:
            _, raw = self._resolver.resolve(raw["$ref"], where)
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{where}: deve ser um objeto.")
        return raw

    def _path_item(self, path: str, item: Mapping[str, Raw], where: str) -> list[Operation]:
        shared = self._parameters(item.get("parameters"), f"{where}/parameters")
        result: list[Operation] = []
        for method in HTTP_METHODS:
            if method in item:
                op_where = f"{where}/{method}"
                node = self._object(item[method], op_where)
                result.append(self._operation(method, path, node, shared, op_where))
        return result

    def _operation(
        self,
        method: HttpMethod,
        path: str,
        node: Mapping[str, Raw],
        shared: dict[tuple[str, str], Parameter],
        where: str,
    ) -> Operation:
        own = self._parameters(node.get("parameters"), f"{where}/parameters")
        operation_id, synthesized = self._identity(method, path, node, where)
        try:
            return Operation(
                operation_id=operation_id,
                id_synthesized=synthesized,
                method=method,
                path=path,
                parameters=tuple({**shared, **own}.values()),
                request_body=self._request_body(node.get("requestBody"), f"{where}/requestBody"),
                success_responses=self._responses(node.get("responses"), f"{where}/responses"),
                security=self._security(node, where),
                tags=_tags(node.get("tags")),
                deprecated=node.get("deprecated") is True,
                summary=_summary(node.get("summary")),
            )
        except ValidationError as error:
            first = error.errors()[0]
            # Só o texto das nossas validações (sem eco do valor) ou o caminho do campo.
            detail = first.get("ctx", {}).get("error") or ".".join(str(p) for p in first["loc"])
            raise ConfigError(
                f"{where}: operação inválida ({detail}).",
                hint="Corrija o trecho indicado do OpenAPI.",
            ) from None

    def _identity(
        self, method: str, path: str, node: Mapping[str, Raw], where: str
    ) -> tuple[str, bool]:
        declared = node.get("operationId")
        if declared is not None:
            if not isinstance(declared, str) or not declared:
                raise ConfigError(f"{where}/operationId: deve ser um texto não vazio.")
            if declared in self._used_ids:
                raise ConfigError(
                    f"{where}: operationId {safe_identifier(declared)} repetido (já usado em "
                    f"{self._used_ids[declared]}).",
                    hint="Cada operação precisa de um operationId único no OpenAPI.",
                )
            self._used_ids[declared] = where
            return declared, False
        base = synthesize_operation_id(method, path)
        candidate, number = base, 2
        while candidate in self._used_ids:
            candidate, number = f"{base}_{number}", number + 1
        self._used_ids[candidate] = where
        return candidate, True

    def _parameters(self, raw: Raw, where: str) -> dict[tuple[str, str], Parameter]:
        if raw is None:
            return {}
        if not isinstance(raw, list):
            raise ConfigError(f"{where}: deve ser uma lista.")
        result: dict[tuple[str, str], Parameter] = {}
        for index, entry in enumerate(raw):
            item_where = f"{where}/{index}"
            parameter = self._parameter(self._object(entry, item_where), item_where)
            result[(parameter.name, parameter.location)] = parameter
        return result

    def _parameter(self, node: Mapping[str, Raw], where: str) -> Parameter:
        name = node.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigError(f"{where}/name: deve ser um texto não vazio.")
        location = next((known for known in _LOCATIONS if known == node.get("in")), None)
        if location is None:
            raise ConfigError(f"{where}/in: deve ser path, query, header ou cookie.")
        schema = node.get("schema")
        content = node.get("content")
        if schema is None and isinstance(content, Mapping):
            schema = _first_media_schema(content)
        converted = self._schemas.convert(schema, f"{where}/schema")
        try:
            return Parameter(
                name=name,
                location=location,
                required=location == "path" or node.get("required") is True,
                value_schema=converted,
            )
        except ValidationError:
            raise ConfigError(f"{where}: parâmetro inválido (nome longo demais?).") from None

    def _media(self, content: Raw, where: str) -> tuple[MediaBody, ...]:
        if content is None:
            return ()
        if not isinstance(content, Mapping):
            raise ConfigError(f"{where}/content: deve ser um objeto.")
        media: list[MediaBody] = []
        for media_type, entry in list(content.items())[:MAX_MEDIA_TYPES]:
            media_where = f"{where}/content/{escape_pointer(str(media_type))}"
            body = self._object(entry, media_where) if entry is not None else {}
            schema = (
                self._schemas.convert(body["schema"], f"{media_where}/schema")
                if "schema" in body
                else None
            )
            media.append(MediaBody(media_type=str(media_type)[:100], body_schema=schema))
        return tuple(media)

    def _request_body(self, raw: Raw, where: str) -> RequestBody | None:
        if raw is None:
            return None
        node = self._object(raw, where)
        return RequestBody(
            required=node.get("required") is True, media=self._media(node.get("content"), where)
        )

    def _responses(self, raw: Raw, where: str) -> tuple[SuccessResponse, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{where}: deve ser um objeto.")
        result: list[SuccessResponse] = []
        for code, entry in raw.items():
            status = str(code).upper()
            if len(status) != 3 or status[0] != "2":
                continue
            node = self._object(entry, f"{where}/{escape_pointer(status)}")
            media = self._media(node.get("content"), f"{where}/{status}")
            result.append(SuccessResponse(status=status, body_schema=_json_schema(media)))
        return tuple(result)

    def _security(self, node: Mapping[str, Raw], where: str) -> tuple[SecurityRequirement, ...]:
        if "security" not in node:
            return self._default_security
        return parse_security(node["security"], f"{where}/security")


def parse_security(raw: Raw, where: str) -> tuple[SecurityRequirement, ...]:
    """Converte `security` (lista de mapas nome -> escopos) em alternativas de segurança."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{where}: deve ser uma lista.")
    result: list[SecurityRequirement] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ConfigError(f"{where}: cada item deve ser um objeto.")
        result.append(SecurityRequirement(schemes=tuple(str(name)[:100] for name in entry)))
    return tuple(result)


def _tags(raw: Raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(tag)[:100] for tag in raw[:_MAX_TAGS] if isinstance(tag, str))


def _summary(raw: Raw) -> str | None:
    """Resumo curto da operação, sem controle e com no máximo 200 caracteres (ou `None`)."""
    if not isinstance(raw, str):
        return None
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", raw).split())
    return cleaned[:_MAX_SUMMARY] or None


def _first_media_schema(content: Mapping[str, Raw]) -> Raw:
    for entry in content.values():
        if isinstance(entry, Mapping) and "schema" in entry:
            return entry["schema"]
    return None


def _json_schema(media: tuple[MediaBody, ...]) -> Schema | None:
    chosen = RequestBody(media=media).preferred()
    return chosen.body_schema if chosen else None
