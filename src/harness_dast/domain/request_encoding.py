"""Codificação de requisições montadas (`BuiltRequest`) e do login em `HttpRequest`.

Aqui nasce a URL absoluta que o `ScopeGuard` vai conferir. Corpo JSON, formulário
(`application/x-www-form-urlencoded`) e texto são suportados; outros tipos de mídia (por
exemplo `multipart/form-data`) viram `ConfigError`, para o agente saber que a operação não
pode ser testada ainda. Este módulo é puro.
"""

import json
from urllib.parse import urlencode

from harness_dast.domain.api_model import safe_identifier
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.auth import PasswordLoginAuth
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.http_messages import HttpRequest, Route
from harness_dast.domain.request_builder import BuiltRequest

LOGIN_OPERATION_ID = "auth.login"
CSRF_OPERATION_ID = "auth.csrf"


def join_url(base_url: str, path: str, query: tuple[tuple[str, str], ...] = ()) -> str:
    """Junta `base_url` e `path` (mantendo prefixo do `base_url`) e acrescenta a consulta."""
    url = base_url.rstrip("/") + path
    return f"{url}?{urlencode(query)}" if query else url


def encode_body(body: JsonValue, media_type: str | None) -> tuple[bytes | None, str | None]:
    """Codifica o corpo conforme o tipo de mídia; devolve (bytes, Content-Type).

    Raises:
        ConfigError: Tipo de mídia não suportado, ou corpo que não cabe no formato.
    """
    if media_type is None or body is None:
        return None, None
    kind = media_type.split(";")[0].strip().lower()
    if kind == "application/json" or kind.endswith("+json"):
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(), kind
    if kind == "application/x-www-form-urlencoded":
        return _form(body).encode(), kind
    if kind == "text/plain":
        return str(body).encode(), kind
    raise ConfigError(
        f"O tipo de mídia {safe_identifier(kind)} do corpo não é suportado pelo probe.",
        hint="Operações multipart ou binárias ainda não são testadas; deixe-a fora do plano.",
    )


def _form(body: JsonValue) -> str:
    if not isinstance(body, dict):
        raise ConfigError(
            "Um corpo de formulário deve ser um objeto de campos simples.",
            hint="Confira o esquema do corpo no OpenAPI.",
        )
    pairs: list[tuple[str, str]] = []
    for name, value in body.items():
        if isinstance(value, dict | list):
            raise ConfigError(
                "Um corpo de formulário não aceita campos aninhados.",
                hint="Confira o esquema do corpo no OpenAPI.",
            )
        pairs.append((name, _form_value(value)))
    return urlencode(pairs)


def _form_value(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def encode_built_request(
    built: BuiltRequest,
    *,
    base_url: str,
    extra_headers: tuple[tuple[str, str], ...] = (),
    account: str | None = None,
) -> HttpRequest:
    """Transforma a requisição montada em `HttpRequest` (ainda sem aprovação do escopo).

    Raises:
        ConfigError: Tipo de mídia do corpo não suportado.
    """
    payload, content_type = encode_body(built.body, built.body_media_type)
    headers: list[tuple[str, str]] = list(built.headers.items())
    if built.cookies:
        headers.append(("Cookie", "; ".join(f"{k}={v}" for k, v in built.cookies.items())))
    if content_type is not None:
        headers.append(("Content-Type", content_type))
    headers.extend(extra_headers)
    return HttpRequest(
        method=built.method,
        url=join_url(base_url, built.path, built.query),
        headers=tuple(headers),
        body=payload,
        operation_id=built.operation_id,
        account=account,
        route="zap",
    )


def build_login_request(
    auth: PasswordLoginAuth,
    *,
    base_url: str,
    account: str,
    username: str,
    password: str,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> HttpRequest:
    """Monta o POST de login conforme `request_encoding` do perfil (sai pela rota `auth`)."""
    fields: dict[str, JsonValue] = {
        auth.username_field: username,
        auth.password_field: password,
    }
    media = (
        "application/json"
        if auth.request_encoding == "json"
        else "application/x-www-form-urlencoded"
    )
    payload, content_type = encode_body(fields, media)
    headers = (("Content-Type", content_type or ""), *extra_headers)
    return HttpRequest(
        method="POST",
        url=join_url(base_url, auth.token_path),
        headers=headers,
        body=payload,
        operation_id=LOGIN_OPERATION_ID,
        account=account,
        route="auth",
    )


def build_get_request(
    *, base_url: str, path: str, operation_id: str, account: str | None, route: Route
) -> HttpRequest:
    """Monta um GET simples (busca de token CSRF, checagem de saúde)."""
    return HttpRequest(
        method="GET",
        url=join_url(base_url, path),
        operation_id=operation_id,
        account=account,
        route=route,
    )
