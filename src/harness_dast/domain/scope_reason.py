"""Códigos estáveis do motivo pelo qual o escopo recusou uma requisição. Módulo puro.

O que garante: cada recusa da normalização e do `ScopeGuard` carrega um código que não depende
do texto da mensagem (a mensagem pode mudar; o código é contrato). O que não faz: não decide
nada; só nomeia.

Os códigos se dividem em dois grupos: os de "decisão de escopo" (o pedido é bem formado, mas
está fora do que a carta permite) e os de "forma" (a URL, o método ou o caminho é ambíguo ou
malformado). O agrupador `is_malformed` existe para quem lê o motivo antigo `malformed_request`,
que reunia todos os de forma.
"""

from enum import StrEnum


class ScopeReason(StrEnum):
    """Motivo estável de uma `ScopeViolation`."""

    # Decisão de escopo.
    DENY_PATH = "deny_path"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    HOST_NOT_ALLOWED = "host_not_allowed"
    PATH_NOT_ALLOWED = "path_not_allowed"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    # Forma: método, URL, esquema, autoridade.
    METHOD_UNKNOWN = "method_unknown"
    URL_MISSING = "url_missing"
    URL_TOO_LONG = "url_too_long"
    URL_FORBIDDEN_CHAR = "url_forbidden_char"
    URL_NOT_ABSOLUTE = "url_not_absolute"
    URL_NOT_ASCII = "url_not_ascii"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    CREDENTIALS_IN_URL = "credentials_in_url"
    PORT_INVALID = "port_invalid"
    HOST_INVALID = "host_invalid"
    # Forma: caminho.
    PATH_EMPTY_SEGMENT = "path_empty_segment"
    PATH_ENCODED_SLASH = "path_encoded_slash"
    PATH_MATRIX_PARAM = "path_matrix_param"
    PATH_TRAILING_DOT_SPACE = "path_trailing_dot_space"
    PATH_DOUBLE_ENCODING = "path_double_encoding"
    PATH_DOT_SEGMENT = "path_dot_segment"
    PATH_BAD_PERCENT = "path_bad_percent"
    PATH_INVALID_UTF8 = "path_invalid_utf8"
    PATH_CONTROL_CHAR = "path_control_char"
    PATH_TOO_MANY_READINGS = "path_too_many_readings"

    @property
    def is_malformed(self) -> bool:
        """`True` para os motivos de forma (o antigo `malformed_request`)."""
        return self not in _SCOPE_DECISIONS

    @property
    def is_path_shape(self) -> bool:
        """`True` para os motivos que dizem respeito ao formato do caminho."""
        return self.is_malformed and self.value.startswith("path_")


_SCOPE_DECISIONS = frozenset(
    {
        ScopeReason.DENY_PATH,
        ScopeReason.ORIGIN_NOT_ALLOWED,
        ScopeReason.HOST_NOT_ALLOWED,
        ScopeReason.PATH_NOT_ALLOWED,
        ScopeReason.METHOD_NOT_ALLOWED,
    }
)

WIDE_READING_OUTSIDE_ALLOW = "wide_reading_outside_allow"
"""Marca do modo amplo: pedido liberado cujo caminho tem uma leitura fora de `scope.allow` (o
risco aceito do ADR 0026). Vai ao campo `detail` da auditoria; não é motivo de recusa."""

PATH_SHAPE_CODES = frozenset(r.value for r in ScopeReason if r.is_path_shape)
"""Códigos (texto) das recusas por formato do caminho; base do aviso de cobertura parcial."""
