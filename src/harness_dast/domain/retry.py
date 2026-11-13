"""Decisão de nova tentativa após uma resposta, com contadores que limitam cada tipo.

Três situações justificam repetir UMA requisição, cada uma com teto próprio (ver
`probe_policy`): 401 de token vencido (login de novo, uma vez; se o perfil declara o sinal de
"token vencido", só o 401 que o traz conta), 403 que parece rejeição de CSRF (buscar o token
de novo, uma vez) e 429 (esperar `Retry-After`, algumas vezes e por tempo limitado).
Qualquer outra resposta encerra a operação. Este módulo é puro.
"""

from typing import Literal

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.http_messages import HttpResponse
from harness_dast.domain.outcome import looks_like_csrf_rejection, parse_json_body
from harness_dast.domain.probe_config import ErrorCodes, JsonFieldRule
from harness_dast.domain.probe_policy import (
    MAX_CSRF_REFRESH_PER_REQUEST,
    MAX_RATE_LIMIT_WAITS,
    MAX_REAUTH_PER_REQUEST,
)

RetryAction = Literal["done", "reauth", "refresh_csrf", "wait"]


class RetryState(ApiModel):
    """Quantas vezes cada tipo de nova tentativa já foi usado para a requisição atual.

    Attributes:
        reauths: Logins repetidos após 401.
        csrf_refreshes: Buscas repetidas do token CSRF.
        waits: Esperas por `Retry-After`.
    """

    reauths: int = 0
    csrf_refreshes: int = 0
    waits: int = 0

    def after(self, action: RetryAction) -> "RetryState":
        """Devolve o estado depois de executar `action` (sem alterar o atual)."""
        return RetryState(
            reauths=self.reauths + (action == "reauth"),
            csrf_refreshes=self.csrf_refreshes + (action == "refresh_csrf"),
            waits=self.waits + (action == "wait"),
        )


def is_token_expired(response: HttpResponse, signal: JsonFieldRule | None) -> bool:
    """Diz se a resposta é o "token vencido" do alvo: 401 e, se declarado, o sinal do corpo."""
    if response.status != 401:
        return False
    return signal is None or signal.is_failure(parse_json_body(response))


def next_action(
    response: HttpResponse,
    method: str,
    *,
    csrf: CsrfConfig | None,
    can_reauth: bool,
    state: RetryState,
    token_expired: JsonFieldRule | None = None,
    error_codes: ErrorCodes | None = None,
) -> RetryAction:
    """Decide o que fazer com a resposta.

    Args:
        response: Resposta recebida.
        method: Método da requisição.
        csrf: Configuração de CSRF do perfil, ou `None`.
        can_reauth: Se a requisição foi feita com sessão de conta que pode refazer o login.
        state: Contadores da requisição atual.
        token_expired: Sinal de "token vencido" do perfil (`auth.token_expired`), ou `None`.
        error_codes: Mapa de códigos de erro do perfil, ou `None`.

    Returns:
        `reauth`, `refresh_csrf` ou `wait` enquanto o teto do tipo não foi atingido;
        `done` caso contrário.
    """
    if (
        can_reauth
        and state.reauths < MAX_REAUTH_PER_REQUEST
        and is_token_expired(response, token_expired)
    ):
        return "reauth"
    if (
        looks_like_csrf_rejection(response, method, csrf, error_codes)
        and state.csrf_refreshes < MAX_CSRF_REFRESH_PER_REQUEST
    ):
        return "refresh_csrf"
    if response.status == 429 and state.waits < MAX_RATE_LIMIT_WAITS:
        return "wait"
    return "done"
