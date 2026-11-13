"""Classificação do resultado de uma operação do `probe`, em regras puras.

O agente lê estas classes para decidir o que corrigir: `validation_error` pede regra de
dados, `conflict` pede valor único, `auth_error` e `csrf_error` pedem conta, papel ou token.
Este módulo é puro.
"""

import json
from typing import Final, Literal

from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.probe_config import JsonFieldRule

Outcome = Literal[
    "success",
    "logical_failure",
    "validation_error",
    "conflict",
    "auth_error",
    "csrf_error",
    "not_found",
    "rate_limited",
    "server_error",
    "client_error",
    "redirect",
    "timeout",
    "skipped_scope",
    "skipped_denied",
    "skipped_destructive",
    "skipped_dependency",
    "build_error",
    "dry_run",
]
"""Classes de resultado.

- Enviadas: `success`, `logical_failure` (2xx mas a regra de corpo do perfil diz falha),
  `validation_error` (400/422), `conflict` (409), `auth_error` (401/403), `csrf_error` (403 de
  CSRF), `not_found` (404/410), `rate_limited` (429), `server_error` (5xx), `client_error`
  (demais 4xx), `redirect` (3xx; nunca seguido) e `timeout`.
- Não enviadas: `skipped_scope`, `skipped_denied`, `skipped_destructive`, `skipped_dependency`,
  `build_error` e `dry_run`.
"""

SENT_OUTCOMES: Final = frozenset(
    {
        "success",
        "logical_failure",
        "validation_error",
        "conflict",
        "auth_error",
        "csrf_error",
        "not_found",
        "rate_limited",
        "server_error",
        "client_error",
        "redirect",
        "timeout",
    }
)

_HTTP_OK_FIRST, _HTTP_OK_LAST = 200, 299
_CSRF_WORDS = ("csrf", "xsrf")
_PLAIN_FORBIDDEN_KEYS = frozenset({"timestamp", "status", "error", "path", "trace"})


def parse_json_body(response: HttpResponse) -> JsonValue:
    """Interpreta o corpo como JSON; corpo vazio, truncado ou inválido vira `None`."""
    if not response.body or response.body_truncated:
        return None
    try:
        parsed: JsonValue = json.loads(response.body)
    except (ValueError, RecursionError):
        return None
    return parsed


def looks_like_csrf_rejection(response: HttpResponse, method: str, csrf: CsrfConfig | None) -> bool:
    """Diz se um 403 parece rejeição de CSRF (e portanto vale renovar o token uma vez).

    Só considera 403 num método que exige o token. Parece CSRF quando o corpo cita
    `csrf`/`xsrf`, ou quando é o 403 "pelado" do Spring (corpo vazio, ou JSON só com
    `timestamp/status/error/path` e sem `message`). Heurística: um 403 de autorização
    também pode ser pelado; o custo é uma única repetição.
    """
    if csrf is None or response.status != 403 or method not in csrf.methods:
        return False
    text = response.body.decode("utf-8", errors="replace").lower()
    if any(word in text for word in _CSRF_WORDS):
        return True
    if not text.strip():
        return True
    parsed = parse_json_body(response)
    return isinstance(parsed, dict) and set(parsed) <= _PLAIN_FORBIDDEN_KEYS


def classify_response(
    response: HttpResponse,
    *,
    method: str,
    success_rule: JsonFieldRule | None,
    csrf: CsrfConfig | None,
) -> Outcome:
    """Classifica uma resposta do alvo.

    Args:
        response: Resposta recebida.
        method: Método da requisição (decide se um 403 é de CSRF).
        success_rule: Regra de corpo do perfil (`probe.success`), ou `None` (vale 2xx).
        csrf: Configuração de CSRF do perfil, ou `None`.
    """
    status = response.status
    if _HTTP_OK_FIRST <= status <= _HTTP_OK_LAST:
        if success_rule is not None and success_rule.is_failure(parse_json_body(response)):
            return "logical_failure"
        return "success"
    if 300 <= status < 400:
        return "redirect"
    return _classify_error(response, method, csrf)


def _classify_error(response: HttpResponse, method: str, csrf: CsrfConfig | None) -> Outcome:
    status = response.status
    if status == 403 and looks_like_csrf_rejection(response, method, csrf):
        return "csrf_error"
    if status in {401, 403}:
        return "auth_error"
    if status in {400, 422}:
        return "validation_error"
    if status == 409:
        return "conflict"
    if status in {404, 410}:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    return "client_error"
