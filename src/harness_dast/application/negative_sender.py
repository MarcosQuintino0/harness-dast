"""Envio do teste negativo: o único ponto que fala com o alvo (ADR 0051).

Todo pedido passa por `OperationDispatcher` sobre o `GuardedSender` (o mesmo caminho do `probe` e
do `authz`: escopo, `deny_paths`, métodos, taxa, janela, prazo, trava e auditoria). Só envia um
alvo derivado de `exchanges.json` (não inventa caminho nem método). Reaproveita `Reply`,
`StopRun` e `INTERRUPTIONS` do `authz_sender`, sem alterá-lo. O corpo da resposta nunca é
guardado fora da memória, e o valor enviado nunca é registrado: só o `operation_id` com o
prefixo `negative:` identifica o pedido na auditoria.
"""

from dataclasses import dataclass
from typing import Literal

from harness_dast.application.authz.sender import Reply, StopRun
from harness_dast.application.common_ports import MutationJournal
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.mutation_guard import begin_mutation, finish_mutation
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.errors import PreflightError, ScopeViolation
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.mutation_snapshot import MutationSnapshot
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES, UNRESPONSIVE_THRESHOLD
from harness_dast.domain.request_encoding import join_url

PREFIX = "negative:"


@dataclass(frozen=True)
class NegativeSettings:
    """Entradas fixas do envio.

    Attributes:
        base_url: URL base do ambiente.
        dispatcher: Despachante (escopo, taxa, janela, prazo, auditoria).
        sessions: Sessões das contas (um login por conta).
        max_requests: Teto de requisições do estágio; as repetições do despachante (429, novo
            login) também contam e nunca o ultrapassam. `None` não limita.
    """

    base_url: str
    dispatcher: OperationDispatcher
    sessions: SessionPool
    max_requests: int | None = None
    product: str = ""
    mutation_journal: MutationJournal | None = None
    credential_fields: frozenset[str] = frozenset()
    prefix: str = PREFIX


class NegativeSender:
    """Envia o pedido de um caso (ou a restauração) com a sessão da conta dona do `probe`.

    Conta as requisições enviadas, as contas que enviaram e as falhas seguidas; levanta
    `StopRun` quando o alvo some em várias requisições em sequência.
    """

    def __init__(self, settings: NegativeSettings) -> None:
        """Cria o emissor.

        Args:
            settings: Entradas fixas do envio.
        """
        self._s = settings
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

    @property
    def journals_mutations(self) -> bool:
        """Indica se efeitos incertos bloqueiam a continuação do estágio."""
        return self._s.mutation_journal is not None

    @property
    def credential_fields(self) -> frozenset[str]:
        """Nomes protegidos do perfil para projeções no diário."""
        return self._s.credential_fields

    def _attempts_left(self, reserve: int) -> int | None:
        if self._s.max_requests is None:
            return None
        return max(self._s.max_requests - self._sent - reserve, 1)

    def send(
        self,
        exchange: ExchangeRecord,
        target: str,
        body: str | None,
        *,
        tag: str = "",
        reserve: int = 0,
        snapshot: MutationSnapshot | None = None,
    ) -> Reply:
        """Envia o método do `exchange` ao `target`, com `body`, pela conta dona do pedido.

        `tag` (por exemplo `restore:`) entra no `operation_id` (`negative:<tag><operação>`) para a
        auditoria distinguir a restauração do caso. `reserve` separa do orçamento requisições que
        ficam para depois (a restauração de um `PUT` ou `PATCH`): as repetições do despachante
        só usam o que sobra, e um 429 que esgota o que sobra volta como resposta, sem repetir.

        Returns:
            A resposta; `Reply.problem` marca escopo recusado (`scope`) ou login recusado
            (`account`).

        Raises:
            StopRun: O alvo ficou sem resposta em várias requisições seguidas.
            WindowClosed: Janela fechada.
            DeadlineReached: Prazo esgotado.
            ExternalToolError: Falha do proxy.
        """
        headers = (
            (("Content-Type", exchange.content_type),) if body and exchange.content_type else ()
        )
        request = HttpRequest(
            method=exchange.method,
            url=join_url(self._s.base_url, target),
            headers=headers,
            body=body.encode("utf-8") if body else None,
            operation_id=f"{self._s.prefix}{tag}{exchange.operation_id}",
            account=exchange.account,
        )
        mutating = exchange.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        key = self._begin_mutation(exchange, snapshot) if mutating else None
        try:
            session = self._s.sessions.get(exchange.account)
            sent = self._s.dispatcher.send(
                request,
                session,
                allow_reauth=True,
                max_attempts=1 if mutating else self._attempts_left(reserve),
            )
        except (WindowClosed, DeadlineReached):
            # Com uma única tentativa, a recusa do portão vem antes de qualquer byte da mutação.
            self._finish_mutation(key, "failed")
            raise
        except ScopeViolation:
            self._finish_mutation(key, "failed")
            return Reply(None, problem="scope")
        except PreflightError:
            self._finish_mutation(key, "failed")
            return Reply(None, problem="account")
        if exchange.account not in self._accounts:
            self._accounts.append(exchange.account)
        self._sent += sent.attempts
        response = sent.response
        if response is not None and response.status < 500:
            self._finish_mutation(key, "observed")
        failed = response is None or response.status in TRANSPORT_FAILURE_STATUSES
        self._failures = self._failures + 1 if failed else 0
        if self._failures >= UNRESPONSIVE_THRESHOLD:
            raise StopRun(
                "stopped_target_unresponsive",
                "O alvo ficou sem resposta em várias requisições seguidas; o negative parou.",
            )
        if response is None:
            return Reply(None)
        return Reply(response.status, location=response.location)

    def _begin_mutation(
        self, exchange: ExchangeRecord, snapshot: MutationSnapshot | None
    ) -> str | None:
        journal = self._s.mutation_journal
        if journal is None:
            return None
        key = mutation_key(
            self._s.product, exchange.operation_id, exchange.account, exchange.method
        )
        begin_mutation(journal, key, snapshot)
        return key

    def _finish_mutation(self, key: str | None, outcome: Literal["failed", "observed"]) -> None:
        if key is not None and self._s.mutation_journal is not None:
            finish_mutation(self._s.mutation_journal, key, outcome)
