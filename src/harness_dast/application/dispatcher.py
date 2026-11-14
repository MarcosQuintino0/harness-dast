"""Envio de uma operação com as repetições permitidas (novo login, novo token CSRF, 429).

Todo POST de login passa pelo orçamento de logins ANTES de sair, inclusive o novo login por
token vencido e a repetição após 429.

O despachante não decide NADA sobre as repetições: pergunta a `domain.retry.next_action`. Cada
envio passa pelo `GuardedSender` (escopo, ritmo, janela, auditoria).
"""

from dataclasses import dataclass
from typing import Protocol

from harness_dast.application.login_budget import LoginBudget, is_login_request
from harness_dast.application.ports import Sleeper
from harness_dast.application.run_support import GuardedSender
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.errors import TargetTimeout, TargetUnreachable
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.probe_config import ErrorCodes, JsonFieldRule
from harness_dast.domain.probe_policy import parse_retry_after
from harness_dast.domain.retry import RetryAction, RetryState, next_action


class SessionHooks(Protocol):
    """O que o despachante precisa da sessão de uma conta."""

    def request_headers(self, method: str) -> tuple[tuple[str, str], ...]:
        """Cabeçalhos de autenticação (e de CSRF, se o método exigir) para a conta."""
        ...

    def relogin(self) -> None:
        """Refaz o login (ou, em chave de API, não faz nada)."""
        ...

    def refresh_csrf(self) -> None:
        """Busca o token CSRF de novo."""
        ...


@dataclass(frozen=True)
class SendOutcome:
    """Resultado de enviar uma operação.

    Attributes:
        response: Última resposta recebida, ou `None` se a última tentativa falhou no transporte.
        transport_error: Erro de transporte da última tentativa (timeout ou alvo inalcançável).
        attempts: Quantas requisições foram enviadas.
    """

    response: HttpResponse | None
    transport_error: TargetTimeout | TargetUnreachable | None
    attempts: int


class OperationDispatcher:
    """Envia uma requisição e repete conforme `retry.next_action`."""

    def __init__(
        self,
        sender: GuardedSender,
        sleeper: Sleeper,
        csrf: CsrfConfig | None,
        *,
        login_budget: LoginBudget | None = None,
        login_path: str | None = None,
        token_expired: JsonFieldRule | None = None,
        error_codes: ErrorCodes | None = None,
    ) -> None:
        """Cria o despachante.

        Args:
            sender: Emissor protegido.
            sleeper: Espera injetada (429).
            csrf: Configuração de CSRF do perfil.
            login_budget: Orçamento de logins; todo POST em `login_path` o consome.
            login_path: Caminho do login do perfil, ou `None` (chave de API).
            token_expired: Sinal de "token vencido" do perfil (`auth.token_expired`).
            error_codes: Mapa de códigos de erro do perfil (`probe.error_codes`).
        """
        self._sender = sender
        self._sleeper = sleeper
        self._csrf = csrf
        self._budget = login_budget
        self._login_path = login_path
        self._token_expired = token_expired
        self._error_codes = error_codes

    def send(
        self, request: HttpRequest, session: SessionHooks | None, *, allow_reauth: bool = True
    ) -> SendOutcome:
        """Envia `request`, acrescentando os cabeçalhos da sessão a cada tentativa.

        Args:
            request: Requisição.
            session: Sessão da conta, ou `None` (sem credencial e sem novo login).
            allow_reauth: Falso nos pedidos com credencial adulterada de propósito: um 401 não
                pode refazer o login (esgotaria o orçamento) nem reenviar o pedido.

        Raises:
            ScopeViolation: Requisição fora do escopo, janela fechada ou prazo esgotado.
            ExternalToolError: O proxy do ZAP não respondeu.
            PreflightError: O novo login (após 401) foi recusado.
        """
        state = RetryState()
        attempts = 0
        while True:
            headers = request.headers + (session.request_headers(request.method) if session else ())
            if self._budget is not None and is_login_request(request, self._login_path):
                self._budget.acquire()
            try:
                response = self._sender.send(request.model_copy(update={"headers": headers}))
            except (TargetTimeout, TargetUnreachable) as error:
                return SendOutcome(None, error, attempts + 1)
            attempts += 1
            action = next_action(
                response,
                request.method,
                csrf=self._csrf,
                can_reauth=session is not None and allow_reauth,
                state=state,
                token_expired=self._token_expired,
                error_codes=self._error_codes,
            )
            if action == "done":
                return SendOutcome(response, None, attempts)
            self._apply(action, response, session)
            state = state.after(action)

    def _apply(
        self, action: RetryAction, response: HttpResponse, session: SessionHooks | None
    ) -> None:
        if action == "wait":
            self._sleeper.sleep(parse_retry_after(response.retry_after))
        elif session is not None and action == "reauth":
            session.relogin()
        elif session is not None and action == "refresh_csrf":
            session.refresh_csrf()
