"""Envio de uma operação com as repetições permitidas (novo login, novo token CSRF, 429).

O despachante não decide NADA sobre as repetições: pergunta a `domain.retry.next_action`. Cada
envio passa pelo `GuardedSender` (escopo, ritmo, janela, auditoria).
"""

from dataclasses import dataclass
from typing import Protocol

from harness_dast.application.ports import Sleeper
from harness_dast.application.run_support import GuardedSender
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.errors import TargetTimeout, TargetUnreachable
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
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

    def __init__(self, sender: GuardedSender, sleeper: Sleeper, csrf: CsrfConfig | None) -> None:
        """Cria o despachante.

        Args:
            sender: Emissor protegido.
            sleeper: Espera injetada (429).
            csrf: Configuração de CSRF do perfil.
        """
        self._sender = sender
        self._sleeper = sleeper
        self._csrf = csrf

    def send(self, request: HttpRequest, session: SessionHooks | None) -> SendOutcome:
        """Envia `request`, acrescentando os cabeçalhos da sessão a cada tentativa.

        Raises:
            ScopeViolation: Requisição fora do escopo, janela fechada ou prazo esgotado.
            ExternalToolError: O proxy do ZAP não respondeu.
            PreflightError: O novo login (após 401) foi recusado.
        """
        state = RetryState()
        attempts = 0
        while True:
            headers = request.headers + (session.request_headers(request.method) if session else ())
            try:
                response = self._sender.send(request.model_copy(update={"headers": headers}))
            except (TargetTimeout, TargetUnreachable) as error:
                return SendOutcome(None, error, attempts + 1)
            attempts += 1
            action = next_action(
                response,
                request.method,
                csrf=self._csrf,
                can_reauth=session is not None,
                state=state,
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
