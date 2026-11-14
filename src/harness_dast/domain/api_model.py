"""Descrição normalizada de uma API, independente da sintaxe do OpenAPI.

O adaptador `adapters/openapi` traduz o documento (3.0 ou 3.1, com `$ref` resolvidas) para
estes modelos. O resto do harness só conhece `ApiSpec` e `Operation`. Todo texto que veio do
documento é NÃO CONFIÁVEL: aqui ele só é guardado e, quando entra numa mensagem, passa por
`safe_identifier`. Este módulo é puro.
"""

import re
from typing import Literal, Self

from pydantic import Field, model_validator

from harness_dast.domain.api_schema import ApiModel, Schema
from harness_dast.domain.errors import ConfigError

HttpMethod = Literal["get", "put", "post", "delete", "options", "head", "patch", "trace"]
ParamLocation = Literal["path", "query", "header", "cookie"]
MAX_OPERATIONS = 5000
MAX_PARAMETERS = 200
MAX_MEDIA_TYPES = 20
_PLACEHOLDER = re.compile(r"\{([^{}/]+)\}")
_NON_WORD = re.compile(r"[^A-Za-z0-9]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_LENGTH = 60


def safe_identifier(text: str) -> str:
    """Devolve `text` seguro para uma mensagem: sem controle, entre aspas e com no máximo 60.

    O texto vem do documento OpenAPI (não confiável): quebra de linha ou sequência de
    escape poderia forjar linhas em logs ou no envelope.
    """
    cleaned = _CONTROL.sub("?", text)
    if len(cleaned) > _SAFE_LENGTH:
        cleaned = cleaned[: _SAFE_LENGTH - 3] + "..."
    return f"'{cleaned}'"


def synthesize_operation_id(method: str, path: str) -> str:
    """Cria um `operation_id` determinístico para uma operação que não declara um.

    Forma: método em minúsculas, segmentos do caminho com caracteres não alfanuméricos
    trocados por `_` e cada `{param}` escrito como `by_param`. Exemplo:
    `GET /users/v1/{username}/email` vira `get_users_v1_by_username_email`. A raiz `/` vira
    `get_root`. O resultado tem no máximo 120 caracteres.
    """
    words: list[str] = [method.lower()]
    for segment in path.split("/"):
        if not segment:
            continue
        placeholder = _PLACEHOLDER.fullmatch(segment)
        text = f"by_{placeholder.group(1)}" if placeholder else segment
        words.append(_NON_WORD.sub("_", text).strip("_"))
    if len(words) == 1:
        words.append("root")
    return "_".join(word for word in words if word)[:120]


class Parameter(ApiModel):
    """Parâmetro de uma operação.

    Attributes:
        name: Nome do parâmetro.
        location: Onde viaja (`path`, `query`, `header` ou `cookie`).
        required: Obrigatório (parâmetros de caminho sempre são).
        value_schema: Esquema do valor.
    """

    name: str = Field(min_length=1, max_length=200)
    location: ParamLocation
    required: bool = False
    value_schema: Schema = Field(default_factory=Schema)


class MediaBody(ApiModel):
    """Corpo de requisição para um tipo de mídia.

    Attributes:
        media_type: Por exemplo `application/json`.
        body_schema: Esquema do corpo, ou `None` se o documento não o descreve.
    """

    media_type: str = Field(min_length=1, max_length=100)
    body_schema: Schema | None = None


class RequestBody(ApiModel):
    """Corpo de requisição de uma operação, por tipo de mídia.

    Attributes:
        required: Se o corpo é obrigatório.
        media: Um item por tipo de mídia, na ordem declarada.
    """

    required: bool = False
    media: tuple[MediaBody, ...] = Field(default=(), max_length=MAX_MEDIA_TYPES)

    def preferred(self) -> MediaBody | None:
        """Escolhe o tipo de mídia a gerar: JSON primeiro; senão, o primeiro declarado."""
        for item in self.media:
            if item.media_type.split(";")[0].strip().lower() == "application/json":
                return item
        for item in self.media:
            if item.media_type.split(";")[0].strip().lower().endswith("+json"):
                return item
        return self.media[0] if self.media else None


class SuccessResponse(ApiModel):
    """Resposta de sucesso declarada (código 2xx).

    Attributes:
        status: Código declarado (`200`, `201`, `2XX`).
        body_schema: Esquema do corpo JSON, ou `None`.
    """

    status: str = Field(min_length=3, max_length=3)
    body_schema: Schema | None = None


class SecurityRequirement(ApiModel):
    """Um conjunto de esquemas de segurança que, juntos, autorizam a operação.

    Attributes:
        schemes: Nomes dos esquemas (vazio = a operação aceita chamada anônima).
    """

    schemes: tuple[str, ...] = ()


class Operation(ApiModel):
    """Uma operação (método + caminho) da API.

    Attributes:
        operation_id: Identificador único; sintetizado quando o documento não declara.
        id_synthesized: Se o `operation_id` foi criado pelo harness.
        method: Método HTTP em minúsculas.
        path: Modelo de caminho, por exemplo `/users/{id}`.
        parameters: Parâmetros de todos os locais.
        request_body: Corpo da requisição, se houver.
        success_responses: Respostas 2xx declaradas.
        security: Alternativas de segurança (qualquer uma serve); vazio = sem exigência.
        tags: Etiquetas declaradas.
        deprecated: Marcada como obsoleta.
        summary: Resumo curto declarado no OpenAPI (`summary`), ou `None`. Texto não confiável:
            serve só de nome para mostrar no painel (V1.2).
    """

    operation_id: str = Field(min_length=1, max_length=200)
    id_synthesized: bool = False
    method: HttpMethod
    path: str = Field(min_length=1, max_length=500)
    parameters: tuple[Parameter, ...] = Field(default=(), max_length=MAX_PARAMETERS)
    request_body: RequestBody | None = None
    success_responses: tuple[SuccessResponse, ...] = ()
    security: tuple[SecurityRequirement, ...] = ()
    tags: tuple[str, ...] = Field(default=(), max_length=20)
    deprecated: bool = False
    summary: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Confere o formato do caminho e do identificador, e que não há parâmetro repetido."""
        if not self.path.startswith("/"):
            raise ValueError("caminho deve começar com '/'")
        if _CONTROL.search(self.operation_id) or _CONTROL.search(self.path):
            raise ValueError("operation_id e caminho não podem ter caracteres de controle")
        keys = [(p.name, p.location) for p in self.parameters]
        if len(set(keys)) != len(keys):
            raise ValueError("parâmetro repetido (mesmo nome e local)")
        return self

    @property
    def success_codes(self) -> tuple[str, ...]:
        """Códigos de sucesso declarados, na ordem do documento."""
        return tuple(response.status for response in self.success_responses)

    @property
    def path_placeholders(self) -> tuple[str, ...]:
        """Nomes dos `{marcadores}` do modelo de caminho, na ordem em que aparecem."""
        return tuple(_PLACEHOLDER.findall(self.path))

    @property
    def requires_auth(self) -> bool:
        """Verdadeiro se TODA alternativa de segurança exige algum esquema."""
        return bool(self.security) and all(item.schemes for item in self.security)

    def success_schema(self) -> Schema | None:
        """Esquema do corpo da primeira resposta de sucesso que declara um."""
        for response in self.success_responses:
            if response.body_schema is not None:
                return response.body_schema
        return None


class ApiSpec(ApiModel):
    """A API inteira: metadados e operações.

    Attributes:
        title: Título declarado (texto do documento; trate como dado).
        version: Versão declarada da API.
        servers: URLs de servidor como declaradas. NÃO definem o escopo: o escopo vem do
            perfil e da autorização, nunca do documento.
        security_schemes: Nome do esquema -> tipo resumido (`http-bearer`, `apiKey-header`).
        operations: Operações na ordem do documento.
    """

    title: str = Field(max_length=200)
    version: str = Field(max_length=100)
    servers: tuple[str, ...] = Field(default=(), max_length=20)
    security_schemes: dict[str, str] = Field(default_factory=dict)
    operations: tuple[Operation, ...] = Field(default=(), max_length=MAX_OPERATIONS)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        """Recusa dois `operation_id` iguais."""
        ids = [operation.operation_id for operation in self.operations]
        if len(set(ids)) != len(ids):
            raise ValueError("operation_id repetido")
        return self

    def get_operation(self, operation_id: str) -> Operation:
        """Devolve a operação pelo identificador.

        Raises:
            ConfigError: Se não existe; a dica lista até 10 identificadores conhecidos.
        """
        for operation in self.operations:
            if operation.operation_id == operation_id:
                return operation
        known = ", ".join(safe_identifier(o.operation_id) for o in self.operations[:10])
        raise ConfigError(
            f"Operação {safe_identifier(operation_id)} não existe no OpenAPI.",
            hint=f"Use um operation_id que exista no OpenAPI. Exemplos: {known}.",
        )

    def has_operation(self, operation_id: str) -> bool:
        """Diz se existe uma operação com esse identificador."""
        return any(op.operation_id == operation_id for op in self.operations)
