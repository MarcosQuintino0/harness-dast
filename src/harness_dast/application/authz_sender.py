"""Envio e linha de base do teste de autorização: o único ponto que fala com o alvo.

Todo pedido das verificações passa por `ReplaySender`, que usa `OperationDispatcher` sobre o
`GuardedSender` (o mesmo caminho do `probe`: escopo, `deny_paths`, métodos, taxa, janela,
prazo, trava e auditoria). Aqui ficam também o resultado acumulado de uma verificação
(`CheckResult`), a parada antecipada (`StopRun`) e as anotações de "não testado". Nenhum valor
de resposta é guardado fora da memória: só veredito, códigos e NOMES de campo seguem adiante.
Uma verificação nova só precisa de um `CheckContext`; não reabre este módulo.

Passa de 300 linhas de propósito: `ReplaySender`, `Reply`, `CheckResult` e as anotações de "não
testado" se referem uns aos outros, e separá-los criaria importação circular sem ganho.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from harness_dast.application.dispatcher import OperationDispatcher, SessionHooks
from harness_dast.application.ports import SecretVault
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_compare import is_success_status
from harness_dast.domain.authz_config import AuthzCheck, AuthzConfig
from harness_dast.domain.authz_matrix_report import AccessMatrixReport
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
        location: Cabeçalho `Location` da resposta, se houve (identifica o recurso criado).
    """

    status: int | None
    body: bytes = b""
    problem: str | None = None
    location: str | None = None
    cors_allow_origin: str | None = None
    cors_allow_credentials: str | None = None


@dataclass
class CheckResult:
    """Resultado acumulado de uma verificação.

    `writes` conta os pedidos de escrita da atribuição em massa (vale o teto da execução) e
    `created` os recursos que um `POST` de teste deixou no alvo. `matrix` é a tabela "quem
    pode o quê" da verificação `access_matrix` (ADR 0041), preenchida também numa parada.
    """

    findings: list[AuthzFinding] = field(default_factory=list)
    not_tested: list[AuthzNotTested] = field(default_factory=list)
    candidates: int = 0
    tested: int = 0
    writes: int = 0
    created: int = 0
    matrix: AccessMatrixReport | None = None


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
        vault: Registro de segredos a mascarar (recebe cada token adulterado antes do envio).
    """

    product: str
    base_url: str
    config: AuthzConfig
    roles: Mapping[str, str]
    operations: Mapping[str, Operation]
    dispatcher: OperationDispatcher
    sessions: SessionPool
    vault: SecretVault
    run_id: str = ""


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
        self._anonymous: dict[str, Reply] = {}

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
        tag: str = "",
        origin: str | None = None,
    ) -> Reply:
        """Repete o pedido gravado com a sessão da conta.

        `tag` (por exemplo `write:`) entra no `operation_id` do pedido (`authz:<tag><operação>`),
        para a auditoria distinguir a escrita em outra conta.

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
        if origin is not None:
            headers = (*headers, ("Origin", origin))
        request = HttpRequest(
            method=method or exchange.method,
            url=join_url(self._s.base_url, exchange.target),
            headers=headers,
            body=payload.encode("utf-8") if payload else None,
            operation_id=f"authz:{tag}{exchange.operation_id}",
            account=account,
        )
        return self._dispatch(request, account)

    def anonymous(self, exchange: ExchangeRecord) -> Reply:
        """Repete o `GET` gravado SEM credencial, uma vez por alvo (depois, do cache).

        Sem sessão, sem cabeçalho de autenticação, sem cookie (`account=None`) e sem novo login.

        Raises:
            StopRun: O alvo ficou sem resposta em várias requisições seguidas.
            WindowClosed: Janela fechada.
            DeadlineReached: Prazo esgotado.
            ExternalToolError: Falha do proxy.
        """
        if exchange.target not in self._anonymous:
            request = self._get(exchange, f"authz:anonymous:{exchange.operation_id}")
            self._anonymous[exchange.target] = self._dispatch(request, None)
        return self._anonymous[exchange.target]

    def tampered(self, exchange: ExchangeRecord, session: SessionHooks) -> Reply:
        """Repete o `GET` gravado com a credencial adulterada de `session`.

        Sai sem cookie (`account=None`) e sem permitir novo login: um 401 é a resposta esperada.

        Raises:
            StopRun: O alvo ficou sem resposta em várias requisições seguidas.
            WindowClosed: Janela fechada.
            DeadlineReached: Prazo esgotado.
            ExternalToolError: Falha do proxy.
        """
        request = self._get(exchange, f"authz:tampered:{exchange.operation_id}")
        return self._dispatch(request, None, session, allow_reauth=False)

    def _get(self, exchange: ExchangeRecord, operation_id: str) -> HttpRequest:
        return HttpRequest(
            method="GET",
            url=join_url(self._s.base_url, exchange.target),
            operation_id=operation_id,
            account=None,
        )

    def _dispatch(
        self,
        request: HttpRequest,
        account: str | None,
        session: SessionHooks | None = None,
        *,
        allow_reauth: bool = True,
    ) -> Reply:
        try:
            if account is not None:
                session = self._s.sessions.get(account)
            sent = self._s.dispatcher.send(request, session, allow_reauth=allow_reauth)
        except (WindowClosed, DeadlineReached):
            raise
        except ScopeViolation:
            return Reply(None, problem="scope")
        except PreflightError:
            return Reply(None, problem="account")
        if account is not None and account not in self._accounts:
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
        return Reply(
            response.status,
            response.body,
            location=response.location,
            cors_allow_origin=response.cors_allow_origin,
            cors_allow_credentials=response.cors_allow_credentials,
        )

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


def usable_baseline(
    check: AuthzCheck, exchange: ExchangeRecord, sender: ReplaySender, out: CheckResult
) -> Reply | None:
    """Linha de base da conta dona, ou `None` (com a anotação em `out`) se não serve.

    Não serve quando o escopo ou o login recusou o pedido, ou quando a conta dona não repetiu
    o pedido com `2xx` agora: sem linha de base não há o que comparar.
    """
    base = sender.baseline(exchange)
    if base.problem is not None:
        out.not_tested.append(problem_note(check, exchange, base))
        return None
    if not is_success_status(base.status):
        out.not_tested.append(
            note(
                check,
                exchange,
                "baseline_failed",
                "A conta dona não repetiu o pedido com sucesso agora "
                f"(status {base.status}); sem linha de base não há o que comparar.",
            )
        )
        return None
    return base


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
