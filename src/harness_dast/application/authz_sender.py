"""Envio e linha de base do teste de autorização: o único ponto que fala com o alvo.

Todo pedido das verificações passa por `ReplaySender`, que usa `OperationDispatcher` sobre o
`GuardedSender` (o mesmo caminho do `probe`: escopo, `deny_paths`, métodos, taxa, janela,
prazo, trava e auditoria). Aqui ficam também o resultado acumulado de uma verificação
(`CheckResult`), a parada antecipada (`StopRun`) e as anotações de "não testado". Nenhum valor
de resposta é guardado fora da memória: só veredito, códigos e NOMES de campo seguem adiante.
Uma verificação nova só precisa de um `CheckContext`; não reabre este módulo.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_config import AuthzCheck, AuthzConfig
from harness_dast.domain.authz_result import AuthzFinding, AuthzNotTested
from harness_dast.domain.errors import ExternalToolError, PreflightError, ScopeViolation
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES, UNRESPONSIVE_THRESHOLD
from harness_dast.domain.probe_result import ProbeStatus
from harness_dast.domain.request_encoding import join_url


class StopRun(Exception):
    """Parada antecipada que o laço traduz em `AuthzOutcome`."""

    def __init__(self, status: ProbeStatus, message: str) -> None:
        """Cria a parada.

        Args:
            status: Estado final do laço (`stopped_*`).
            message: Explicação da parada.
        """
        super().__init__(message)
        self.status = status
        self.message = message


INTERRUPTIONS = (StopRun, WindowClosed, DeadlineReached, ExternalToolError)
"""Paradas que interrompem o laço; depois de um `PUT` a restauração ainda é tentada."""


@dataclass(frozen=True)
class Reply:
    """Resposta reduzida ao que as decisões usam (o corpo só vive em memória).

    Attributes:
        status: Código HTTP, ou `None` sem resposta.
        body: Corpo da resposta (nunca gravado).
        problem: `scope` (pedido recusado pelo escopo) ou `account` (login recusado), ou `None`.
    """

    status: int | None
    body: bytes = b""
    problem: str | None = None


@dataclass
class CheckResult:
    """Resultado acumulado de uma verificação."""

    findings: list[AuthzFinding] = field(default_factory=list)
    not_tested: list[AuthzNotTested] = field(default_factory=list)
    candidates: int = 0
    tested: int = 0


@dataclass(frozen=True)
class AuthzSettings:
    """Entradas fixas do laço.

    Attributes:
        product: Produto.
        base_url: URL base do ambiente.
        config: Bloco `authz` do perfil.
        roles: Papel de cada conta (apelido -> papel).
        operations: Operações do OpenAPI por identificador.
        dispatcher: Despachante (escopo, taxa, janela, prazo, auditoria).
        sessions: Sessões das contas (um login por conta).
    """

    product: str
    base_url: str
    config: AuthzConfig
    roles: Mapping[str, str]
    operations: Mapping[str, Operation]
    dispatcher: OperationDispatcher
    sessions: SessionPool


class ReplaySender:
    """Repete pedidos gravados e guarda a linha de base de cada conta e caminho.

    Só REPETE o que está em `exchanges.json`: monta a URL a partir do alvo gravado e não
    inventa caminho nem método. Conta as requisições enviadas, as contas que enviaram e as
    falhas seguidas; levanta `StopRun` quando o alvo some em várias requisições em sequência.
    """

    def __init__(self, settings: AuthzSettings) -> None:
        """Cria o emissor.

        Args:
            settings: Entradas fixas do laço.
        """
        self._s = settings
        self._cache: dict[tuple[str, str], Reply] = {}
        self._sent = 0
        self._failures = 0
        self._accounts: list[str] = []

    @property
    def sent(self) -> int:
        """Requisições enviadas, contando as retentativas."""
        return self._sent

    @property
    def accounts(self) -> tuple[str, ...]:
        """Contas que enviaram, na ordem do primeiro envio."""
        return tuple(self._accounts)

    def send(
        self,
        exchange: ExchangeRecord,
        account: str,
        *,
        body: JsonValue = None,
        with_body: bool = False,
        method: str | None = None,
    ) -> Reply:
        """Repete o pedido gravado com a sessão da conta.

        Returns:
            A resposta; `Reply.problem` marca escopo recusado ou login recusado.

        Raises:
            StopRun: O alvo ficou sem resposta em várias requisições seguidas.
            WindowClosed: Janela fechada.
            DeadlineReached: Prazo esgotado.
            ExternalToolError: Falha do proxy.
        """
        text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if with_body else None
        payload = text if text is not None else exchange.body
        headers = (
            (("Content-Type", exchange.content_type),) if payload and exchange.content_type else ()
        )
        request = HttpRequest(
            method=method or exchange.method,
            url=join_url(self._s.base_url, exchange.target),
            headers=headers,
            body=payload.encode("utf-8") if payload else None,
            operation_id=f"authz:{exchange.operation_id}",
            account=account,
        )
        try:
            session = self._s.sessions.get(account)
            sent = self._s.dispatcher.send(request, session)
        except (WindowClosed, DeadlineReached):
            raise
        except ScopeViolation:
            return Reply(None, problem="scope")
        except PreflightError:
            return Reply(None, problem="account")
        if account not in self._accounts:
            self._accounts.append(account)
        self._sent += sent.attempts
        response = sent.response
        failed = response is None or response.status in TRANSPORT_FAILURE_STATUSES
        self._failures = self._failures + 1 if failed else 0
        if self._failures >= UNRESPONSIVE_THRESHOLD:
            raise StopRun(
                "stopped_target_unresponsive",
                "O alvo ficou sem resposta em várias requisições seguidas; o authz parou.",
            )
        if response is None:
            return Reply(None)
        return Reply(response.status, response.body)

    def baseline(self, exchange: ExchangeRecord) -> Reply:
        """Resposta da conta dona ao pedido gravado (uma vez por conta e caminho)."""
        key = (exchange.account, exchange.target)
        if key not in self._cache:
            self._cache[key] = self.send(exchange, exchange.account)
        return self._cache[key]


class CheckContext:
    """O que toda verificação recebe: entradas fixas, emissor e registro do resultado vivo.

    O registro (`begin`) existe para que uma parada no meio de uma verificação não perca o
    que ela já acumulou: o laço o devolve como `partial`.
    """

    def __init__(self, settings: AuthzSettings, sender: ReplaySender) -> None:
        """Cria o contexto.

        Args:
            settings: Entradas fixas do laço.
            sender: Emissor compartilhado (contadores e linha de base valem para todas).
        """
        self.settings = settings
        self.sender = sender
        self.volatile = settings.config.volatile_names()
        self.live: dict[AuthzCheck, CheckResult] = {}

    def begin(self, check: AuthzCheck, result: CheckResult) -> CheckResult:
        """Registra o resultado em andamento e o devolve."""
        self.live[check] = result
        return result


def note(check: AuthzCheck, exchange: ExchangeRecord, reason: str, message: str) -> AuthzNotTested:
    """Anotação de operação não testada, com motivo e mensagem."""
    return AuthzNotTested(
        check=check,
        operation_id=exchange.operation_id,
        method=exchange.method,
        path=exchange.path,
        reason=reason,
        message=message,
    )


def problem_note(check: AuthzCheck, exchange: ExchangeRecord, reply: Reply) -> AuthzNotTested:
    """Anotação para pedido recusado pelo escopo ou conta sem sessão."""
    if reply.problem == "scope":
        return note(
            check,
            exchange,
            "scope_denied",
            "O escopo do perfil recusou o pedido (caminho negado ou método fora do escopo); "
            "nada foi enviado.",
        )
    return note(
        check,
        exchange,
        "account_unavailable",
        "Uma conta necessária não conseguiu abrir sessão (login recusado).",
    )


def inconclusive(check: AuthzCheck, exchange: ExchangeRecord, reply: Reply) -> AuthzNotTested:
    """Anotação para resposta sem conclusão (não conta como seguro)."""
    return note(
        check,
        exchange,
        "inconclusive",
        f"Resposta sem conclusão (status {reply.status}); não conta como seguro.",
    )
