"""`exchanges.json`: o que o `probe` enviou com sucesso, para o teste de autorização repetir.

O `probe.json` só tem o modelo de caminho e a auditoria só tem o caminho sem consulta; para
repetir "o mesmo pedido" com outra conta é preciso lembrar o alvo concreto (com o identificador
do recurso). Este arquivo guarda, só de operações com sucesso: método, modelo de caminho, alvo
concreto relativo à `base_url`, conta, status e, para `POST`, `PUT` e `PATCH` com corpo JSON, o
corpo enviado. Para `multipart/form-data` (ADR 0052) guarda só o resumo das partes (nome, tipo
e tamanho), nunca o corpo, o arquivo, os valores dos campos nem a fronteira.

Nunca entra segredo: o registro é descartado se um segredo registrado aparece no alvo ou no
corpo, e campo de corpo com nome de segredo é removido (e listado em `omitted_fields`). O corpo
das RESPOSTAS nunca é gravado. Este módulo é puro.
"""

import json
from typing import Final

from pydantic import Field, StrictInt, ValidationError, field_validator

from harness_dast.domain.api_schema import ApiModel, JsonValue
from harness_dast.domain.authz.sensitive import classify_field_name
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.multipart_encoding import (
    MULTIPART_MEDIA_TYPE,
    MultipartSummary,
    summarize_multipart,
)
from harness_dast.domain.redaction import Masker

EXCHANGES_SCHEMA_VERSION: Final = 1
BODY_METHODS: Final = frozenset({"POST", "PUT", "PATCH"})
MAX_BODY_CHARS: Final = 20_000
_MAX_DEPTH: Final = 8


class ExchangeRecord(ApiModel):
    """Um pedido do `probe` que teve sucesso, pronto para ser repetido.

    Attributes:
        operation_id: Operação de origem.
        method: Método HTTP.
        path: Modelo de caminho do OpenAPI.
        target: Caminho concreto e consulta, relativos à `base_url` (`/api/consultas/2`).
        account: Apelido da conta que enviou.
        status: Código HTTP recebido.
        content_type: `Content-Type` do corpo enviado, ou `None` sem corpo (em multipart, só
            `multipart/form-data`, sem a fronteira).
        body: Corpo JSON enviado (só POST, PUT e PATCH), ou `None`.
        omitted_fields: Campos do corpo removidos por terem nome de segredo.
        multipart: Resumo das partes de um corpo multipart (sem valores), ou `None`. Um registro
            com `multipart` não é reexecutável: `authz` e `negative` o tratam como
            `unsupported_body`.
    """

    operation_id: str
    method: str
    path: str
    target: str
    account: str
    status: int
    content_type: str | None = None
    body: str | None = Field(default=None, max_length=MAX_BODY_CHARS)
    omitted_fields: tuple[str, ...] = ()
    multipart: MultipartSummary | None = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        """Só caminho relativo à `base_url`: um alvo adulterado nunca troca o host.

        Defesa em profundidade: o `ScopeGuard` continua sendo quem decide o escopo.
        """
        if (
            not value.startswith("/")
            or value.startswith("//")
            or any(char in value for char in "\\ \t\r\n#")
            or not value.isprintable()
        ):
            raise ValueError("target precisa ser um caminho relativo simples, começando por '/'")
        return value


class ExchangeLog(ApiModel):
    """Conteúdo de `exchanges.json`.

    Attributes:
        schema_version: Versão do formato.
        run_id: Execução do `probe`.
        product: Produto.
        exchanges: Pedidos com sucesso, na ordem em que o `probe` os enviou.
        next_unique_counter: Próxima posição de geração única; `None` em registros antigos.
    """

    schema_version: int = EXCHANGES_SCHEMA_VERSION
    run_id: str
    product: str
    exchanges: tuple[ExchangeRecord, ...] = ()
    next_unique_counter: StrictInt | None = Field(default=None, ge=0, le=65536)


def _drop_secret_fields(value: JsonValue, omitted: list[str], depth: int = 0) -> JsonValue:
    if depth > _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        kept: dict[str, JsonValue] = {}
        for name, item in value.items():
            if classify_field_name(name) == "secret":
                omitted.append(name)
            else:
                kept[name] = _drop_secret_fields(item, omitted, depth + 1)
        return kept
    if isinstance(value, list):
        return [_drop_secret_fields(item, omitted, depth + 1) for item in value]
    return value


def _header(request: HttpRequest, name: str) -> str | None:
    for key, value in request.headers:
        if key.lower() == name:
            return value
    return None


def _body_of(request: HttpRequest, mask: Masker) -> tuple[str | None, tuple[str, ...], bool]:
    """Corpo gravável, campos omitidos e se o registro deve ser descartado."""
    if request.method not in BODY_METHODS or not request.body:
        return None, (), False
    content_type = (_header(request, "content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json" and not content_type.endswith("+json"):
        return None, (), False
    try:
        parsed: JsonValue = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, (), False
    omitted: list[str] = []
    cleaned = _drop_secret_fields(parsed, omitted)
    text = json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)
    if mask(text) != text or len(text) > MAX_BODY_CHARS:
        return None, (), True
    return text, tuple(dict.fromkeys(omitted)), False


def _multipart_of(
    request: HttpRequest, mask: Masker
) -> tuple[MultipartSummary | None, tuple[str, ...], bool]:
    """Resumo do multipart, campos omitidos e se o registro deve ser descartado."""
    content_type = _header(request, "content-type") or ""
    if (
        request.method not in BODY_METHODS
        or not request.body
        or content_type.split(";")[0].strip().lower() != MULTIPART_MEDIA_TYPE
    ):
        return None, (), False
    text = request.body.decode("latin-1")
    summary = summarize_multipart(content_type, request.body)
    if summary is None or mask(text) != text:
        return None, (), True
    omitted = [
        part.name
        for part in summary.parts
        if part.kind == "field" and classify_field_name(part.name) == "secret"
    ]
    kept = tuple(part for part in summary.parts if part.name not in omitted)
    return summary.model_copy(update={"parts": kept}), tuple(omitted), False


def _recorded_content_type(body: str | None, multipart: MultipartSummary | None) -> str | None:
    if multipart is not None:
        return MULTIPART_MEDIA_TYPE
    return "application/json" if body is not None else None


def build_exchange(
    *,
    request: HttpRequest,
    path_template: str,
    status: int,
    base_url: str,
    mask: Masker,
) -> ExchangeRecord | None:
    """Registro repetível de um pedido com sucesso, ou `None` se não pode ser guardado.

    Devolve `None` quando a requisição é anônima, a URL não está sob `base_url` ou o alvo não é
    um caminho relativo simples, o alvo ou o corpo carregam um segredo registrado (`mask` muda o
    texto) ou o corpo é grande demais.
    """
    prefix = base_url.rstrip("/")
    if request.account is None or not request.url.startswith(prefix):
        return None
    target = request.url[len(prefix) :]
    if not target.startswith("/") or mask(target) != target:
        return None
    body, omitted, discard = _body_of(request, mask)
    multipart, multipart_omitted, discard_multipart = _multipart_of(request, mask)
    if discard or discard_multipart:
        return None
    try:
        return ExchangeRecord(
            operation_id=request.operation_id,
            method=request.method,
            path=path_template,
            target=target,
            account=request.account,
            status=status,
            content_type=_recorded_content_type(body, multipart),
            body=body,
            omitted_fields=(*omitted, *multipart_omitted),
            multipart=multipart,
        )
    except ValidationError:
        return None
