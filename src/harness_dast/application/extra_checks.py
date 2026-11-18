"""Checagens próprias da V1.12: limite de consumo (F5) e inventário (F8), ADR 0101 e 0102.

Cada pedido sai pelo MESMO caminho do `negative` e do SSRF guiado (`NegativeSender` sobre
`OperationDispatcher` e `GuardedSender`): `ScopeGuard`, `deny_paths`, métodos, taxa, janela,
prazo, trava de emergência, auditoria (prefixos `rate:` e `inventory:`) e diário de mutações
valem. Nada aqui decide escopo, teto ou veredito: isso é do domínio (`rate_page`,
`rate_attempts`, `inventory_checks`). O corpo da resposta nunca é guardado, e o valor enviado nunca
é registrado. O `scan` chama este módulo depois das varreduras do ZAP e anexa os alertas ao fluxo
normal; cada chave da carta (`extra_checks.allow_rate_tests`, `extra_checks.inventory`) liga a sua
checagem, e desligada ela não manda nenhum pedido.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

import structlog

from harness_dast.application.account_session import AccountSession
from harness_dast.application.authz.sender import Reply, StopRun
from harness_dast.application.common_ports import Clock, MutationJournal
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.negative_sender import NegativeSender, NegativeSettings
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.errors import ExternalToolError, PreflightError, ScopeViolation
from harness_dast.domain.extra_check_result import (
    ExtraCheckResult,
    ExtraChecksSummary,
    ExtraSkip,
    ResultOutcome,
)
from harness_dast.domain.inventory_checks import (
    INVENTORY_MAX_REQUESTS,
    InventoryPlan,
    SiblingFamily,
    doc_text,
    docs_alert,
    judge_sibling,
    plan_inventory,
    read_docs,
    sibling_alert,
)
from harness_dast.domain.knowledge_mutation import MutationPending
from harness_dast.domain.probe_exchange import ExchangeLog, ExchangeRecord
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.rate_attempts import (
    ATTEMPT_MAX_REQUESTS,
    ATTEMPTS_PER_OPERATION,
    AttemptCase,
    AttemptPlan,
    AttemptReply,
    attempts_alert,
    first_reply_problem,
    limit_signal,
    plan_attempts,
    reply_text,
)
from harness_dast.domain.rate_page import (
    PAGE_MAX_OPERATIONS,
    PageCase,
    PagePlan,
    judge_page,
    page_alert,
    plan_page_checks,
    read_reply,
)
from harness_dast.domain.request_encoding import join_url
from harness_dast.domain.scope import OutboundRequest

RATE_PREFIX: Final = "rate:"
"""Prefixo do `operation_id` na auditoria dos pedidos de limite de consumo."""

INVENTORY_PREFIX: Final = "inventory:"
"""Prefixo do `operation_id` na auditoria dos pedidos do inventário."""

RATE_MAX_REQUESTS: Final = PAGE_MAX_OPERATIONS * 2 + ATTEMPT_MAX_REQUESTS
"""Teto rígido de pedidos do limite de consumo por execução (6 de tamanho de página + 60)."""

_log = structlog.get_logger()
_PAGE_OUTCOME: Final[dict[str, ResultOutcome]] = {
    "accepted": "finding",
    "limited": "limited",
    "inconclusive": "inconclusive",
}
_SIBLING_OUTCOME: Final[dict[str, ResultOutcome]] = {
    "exists": "finding",
    "absent": "absent",
    "unclear": "inconclusive",
}
_STOPS = (StopRun, WindowClosed, DeadlineReached, ExternalToolError)


class CheckSender(Protocol):
    """Emissor dos pedidos (na prática o `NegativeSender` com o prefixo da checagem)."""

    @property
    def sent(self) -> int:
        """Requisições enviadas, contando as retentativas."""
        ...

    def send(
        self, exchange: ExchangeRecord, target: str, body: str | None, *, tag: str = ""
    ) -> Reply:
        """Envia o método do `exchange` ao `target`, com `body`, pela conta dona do pedido."""
        ...


@dataclass(frozen=True)
class ExtraOutcome:
    """Resultado das checagens extras.

    Attributes:
        rate: Resumo do limite de consumo; `None` com a chave desligada.
        inventory: Resumo do inventário; `None` com a chave desligada.
        alerts: Alertas no formato do ZAP, um por achado.
    """

    rate: ExtraChecksSummary | None
    inventory: ExtraChecksSummary | None
    alerts: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ExtraContext:
    """Entradas das checagens extras.

    Attributes:
        profile: Perfil do produto (chaves, escopo, contas, URL base).
        operations: Operações do OpenAPI por identificador.
        exchanges: Pedidos que o `probe` provou.
        dispatcher: Despachante (escopo, taxa, janela, prazo, auditoria).
        session_factory: Cria a sessão (fechada) de um apelido de conta.
        account: Conta que envia os pedidos (a do `probe`).
        only: Operações do `--only`; vazio = todas.
        product: Nome do produto (chave do diário de mutações).
        mutation_journal: Diário de mutações, ou `None`.
    """

    profile: ProductProfile
    operations: Mapping[str, Operation]
    exchanges: ExchangeLog
    dispatcher: OperationDispatcher
    session_factory: Callable[[str], AccountSession]
    account: str
    only: frozenset[str]
    product: str
    mutation_journal: MutationJournal | None = None
    run_id: str = ""
    clock: Clock | None = None


def _settings(
    ctx: ExtraContext, pool: SessionPool, *, prefix: str, cap: int, attempts: bool = False
) -> NegativeSettings:
    return NegativeSettings(
        base_url=ctx.profile.environment.base_url,
        dispatcher=ctx.dispatcher,
        sessions=pool,
        max_requests=cap,
        product=ctx.product,
        run_id=ctx.run_id,
        clock=ctx.clock,
        mutation_journal=ctx.mutation_journal,
        prefix=prefix,
        rejection_attempts=attempts,
    )


def _permits(profile: ProductProfile) -> Callable[[str, str], bool]:
    guard = profile.guard()
    base_url = profile.environment.base_url

    def permits(method: str, target: str) -> bool:
        url = join_url(base_url, target)
        return guard.evaluate(OutboundRequest(method=method, url=url)).verdict == "allowed"

    return permits


def _identity(pool: SessionPool, account: str) -> str | None:
    """Usuário da conta de teste (o identificador do corpo), ou `None` se o login não abriu."""
    try:
        return pool.get(account).username
    except (PreflightError, ScopeViolation):
        return None


def not_run_outcome(profile: ProductProfile, reason: str) -> ExtraOutcome | None:
    """Resumo de "não executado" para as chaves ligadas (nenhum pedido foi enviado)."""
    flags = profile.extra_checks

    def summary(cap: int) -> ExtraChecksSummary:
        return ExtraChecksSummary(enabled=True, cap=cap, note=f"Não executado: {reason}")

    if not (flags.allow_rate_tests or flags.inventory):
        return None
    return ExtraOutcome(
        rate=summary(RATE_MAX_REQUESTS) if flags.allow_rate_tests else None,
        inventory=summary(INVENTORY_MAX_REQUESTS) if flags.inventory else None,
        alerts=(),
    )


def run_extra_checks(ctx: ExtraContext) -> ExtraOutcome | None:
    """Roda as checagens que a carta ligou; `None` se nenhuma está ligada.

    Nunca levanta por parada do alvo ou da janela: a parada vira nota no resumo, e o que já foi
    concluído é mantido.
    """
    flags = ctx.profile.extra_checks
    if not (flags.allow_rate_tests or flags.inventory):
        return None
    pool = SessionPool(ctx.session_factory)
    permits = _permits(ctx.profile)
    alerts: list[dict[str, str]] = []
    rate = inventory = None
    if flags.allow_rate_tests:
        rate = _rate(ctx, pool, permits, alerts)
    if flags.inventory:
        inventory = _inventory(ctx, pool, permits, alerts)
    return ExtraOutcome(rate=rate, inventory=inventory, alerts=tuple(alerts))


def _rate(
    ctx: ExtraContext,
    pool: SessionPool,
    permits: Callable[[str, str], bool],
    alerts: list[dict[str, str]],
) -> ExtraChecksSummary:
    infrastructure = ctx.profile.infrastructure_paths
    pages = plan_page_checks(
        ctx.exchanges.exchanges,
        ctx.operations,
        permits=permits,
        infrastructure=infrastructure,
        only=ctx.only,
    )
    attempts = plan_attempts(
        ctx.operations,
        identity=_identity(pool, ctx.account),
        permits=permits,
        infrastructure=infrastructure,
        only=ctx.only,
    )
    sender = NegativeSender(
        _settings(ctx, pool, prefix=RATE_PREFIX, cap=RATE_MAX_REQUESTS, attempts=True)
    )
    checks = RateChecks(sender, base_url=ctx.profile.environment.base_url, account=ctx.account)
    summary, found = checks.run(pages, attempts)
    alerts.extend(found)
    return summary


def _inventory(
    ctx: ExtraContext,
    pool: SessionPool,
    permits: Callable[[str, str], bool],
    alerts: list[dict[str, str]],
) -> ExtraChecksSummary:
    plan = plan_inventory(ctx.operations, ctx.exchanges.exchanges, permits=permits, only=ctx.only)
    sender = NegativeSender(
        _settings(ctx, pool, prefix=INVENTORY_PREFIX, cap=INVENTORY_MAX_REQUESTS)
    )
    checks = InventoryChecks(sender, base_url=ctx.profile.environment.base_url, account=ctx.account)
    summary, found = checks.run(plan)
    alerts.extend(found)
    return summary


class RateChecks:
    """Limite de consumo: tamanho de página enorme e tentativas repetidas (ADR 0101)."""

    def __init__(self, sender: CheckSender, *, base_url: str, account: str) -> None:
        """Cria a checagem.

        Args:
            sender: Emissor dos pedidos (prefixo `rate:`).
            base_url: URL base do ambiente.
            account: Conta de teste que envia as tentativas sintéticas.
        """
        self._sender = sender
        self._base_url = base_url
        self._account = account
        self._results: list[ExtraCheckResult] = []
        self._alerts: list[dict[str, str]] = []

    def run(
        self, pages: PagePlan, attempts: AttemptPlan
    ) -> tuple[ExtraChecksSummary, tuple[dict[str, str], ...]]:
        """Envia os pedidos planejados e devolve o resumo e os alertas dos achados."""
        note: str | None = None
        try:
            for case in pages.cases:
                self._page(case)
            for attempt in attempts.cases:
                self._attempts(attempt)
        except _STOPS as stop:
            note = f"A checagem parou antes de terminar: {stop}"
            _log.warning("rate_checks_stopped", reason=str(stop))
        summary = ExtraChecksSummary(
            enabled=True,
            cap=RATE_MAX_REQUESTS,
            sent=self._sender.sent,
            findings=len(self._alerts),
            results=tuple(self._results),
            skipped=(*pages.skipped, *attempts.skipped),
            note=note,
        )
        return summary, tuple(self._alerts)

    def _page(self, case: PageCase) -> None:
        subject = case.operation_id
        base = self._sender.send(case.exchange, case.base_target, None)
        if base.problem is not None:
            self._refused("page_size", subject, base.problem, 1)
            return
        huge = self._sender.send(case.exchange, case.huge_target, None)
        if huge.problem is not None:
            self._refused("page_size", subject, huge.problem, 2)
            return
        verdict = judge_page(
            read_reply(base.status, base.body, truncated=base.body_truncated),
            read_reply(huge.status, huge.body, truncated=huge.body_truncated),
            case.maximum,
        )
        if verdict.outcome == "accepted":
            index = len(self._alerts) + 1
            self._alerts.append(page_alert(index, case, verdict.detail, base_url=self._base_url))
        self._results.append(
            ExtraCheckResult(
                check="page_size",
                subject=subject,
                outcome=_PAGE_OUTCOME[verdict.outcome],
                requests=2,
                detail=verdict.detail,
            )
        )

    def _refused(self, check: str, subject: str, problem: str, requests: int) -> None:
        self._results.append(
            ExtraCheckResult(
                check=check,
                subject=subject,
                outcome="inconclusive",
                requests=requests,
                detail=f"pedido recusado ({problem})",
            )
        )

    def _attempts(self, case: AttemptCase) -> None:
        exchange = ExchangeRecord(
            operation_id=case.operation_id,
            method="POST",
            path=case.path,
            target=case.path,
            account=self._account,
            status=0,
            content_type="application/json",
            body=case.body,
        )
        first: int | None = None
        status: int | None = None
        count = 0
        while count < ATTEMPTS_PER_OPERATION and self._sender.sent < RATE_MAX_REQUESTS:
            try:
                reply = self._sender.send(exchange, case.path, case.body)
            except MutationPending:
                self._attempt_result(case, "inconclusive", count, "mutation_pending")
                return
            if reply.problem is not None:
                self._refused("attempts", case.operation_id, reply.problem, count + 1)
                return
            count += 1
            status = reply.status
            current = AttemptReply(status, reply.retry_after, reply_text(reply.body))
            if status is not None and status >= 500:
                self._attempt_result(case, "inconclusive", count, f"server_error_http_{status}")
                return
            if count == 1:
                problem = first_reply_problem(current)
                if problem is not None:
                    detail = (
                        "possible_state_change: o valor errado foi aceito (2xx)"
                        if problem == "unexpected_success"
                        else problem
                    )
                    self._attempt_result(case, "inconclusive", count, detail)
                    return
                first = status
            signal = limit_signal(current, first)
            if signal is not None:
                self._attempt_result(case, "limited", count, f"sinal de limite: {signal}")
                return
        if count < ATTEMPTS_PER_OPERATION:
            self._attempt_result(case, "inconclusive", count, "teto de pedidos da execução")
            return
        index = len(self._alerts) + 1
        self._alerts.append(attempts_alert(index, case, count, status, base_url=self._base_url))
        self._attempt_result(
            case, "finding", count, f"{count} tentativas sem sinal de limite (HTTP {status})"
        )

    def _attempt_result(
        self, case: AttemptCase, outcome: ResultOutcome, count: int, detail: str
    ) -> None:
        self._results.append(
            ExtraCheckResult(
                check="attempts",
                subject=case.operation_id,
                outcome=outcome,
                requests=count,
                detail=detail,
            )
        )


class InventoryChecks:
    """Inventário: versões irmãs não documentadas e documentação exposta (ADR 0102)."""

    def __init__(self, sender: CheckSender, *, base_url: str, account: str) -> None:
        """Cria a checagem.

        Args:
            sender: Emissor dos pedidos `GET` (prefixo `inventory:`).
            base_url: URL base do ambiente.
            account: Conta de teste que envia os pedidos.
        """
        self._sender = sender
        self._base_url = base_url
        self._account = account
        self._results: list[ExtraCheckResult] = []
        self._alerts: list[dict[str, str]] = []
        self._skipped: list[ExtraSkip] = []

    def run(self, plan: InventoryPlan) -> tuple[ExtraChecksSummary, tuple[dict[str, str], ...]]:
        """Envia os `GET` planejados e devolve o resumo e os alertas dos achados."""
        note: str | None = None
        try:
            for family in plan.families:
                self._family(family)
            for target in plan.docs:
                self._docs(target)
        except _STOPS as stop:
            note = f"A checagem parou antes de terminar: {stop}"
            _log.warning("inventory_checks_stopped", reason=str(stop))
        summary = ExtraChecksSummary(
            enabled=True,
            cap=INVENTORY_MAX_REQUESTS,
            sent=self._sender.sent,
            findings=len(self._alerts),
            results=tuple(self._results),
            skipped=(*plan.skipped, *self._skipped),
            note=note,
        )
        return summary, tuple(self._alerts)

    def _get(self, operation_id: str, target: str) -> Reply:
        exchange = ExchangeRecord(
            operation_id=operation_id,
            method="GET",
            path=target,
            target=target,
            account=self._account,
            status=0,
        )
        return self._sender.send(exchange, target, None)

    def _family(self, family: SiblingFamily) -> None:
        control = self._get(family.operation_id, family.control)
        if control.problem is not None:
            self._skipped.append(
                ExtraSkip(subject=family.control, reason=f"refused_{control.problem}")
            )
            return
        for target in family.siblings:
            reply = self._get(family.operation_id, target)
            if reply.problem is not None:
                self._skipped.append(ExtraSkip(subject=target, reason=f"refused_{reply.problem}"))
                continue
            verdict = judge_sibling(reply.status, control.status)
            if verdict == "exists" and reply.status is not None:
                index = len(self._alerts) + 1
                self._alerts.append(
                    sibling_alert(
                        index, family.operation_id, target, reply.status, base_url=self._base_url
                    )
                )
            self._results.append(
                ExtraCheckResult(
                    check="sibling",
                    subject=target,
                    outcome=_SIBLING_OUTCOME[verdict],
                    requests=1,
                    detail=f"HTTP {reply.status}; controle HTTP {control.status}",
                )
            )

    def _docs(self, target: str) -> None:
        reply = self._get("docs", target)
        if reply.problem is not None:
            self._skipped.append(ExtraSkip(subject=target, reason=f"refused_{reply.problem}"))
            return
        reading = read_docs(reply.status, doc_text(reply.body))
        if reading is not None:
            index = len(self._alerts) + 1
            self._alerts.append(docs_alert(index, target, reading, base_url=self._base_url))
        self._results.append(
            ExtraCheckResult(
                check="docs",
                subject=target,
                outcome="finding" if reading is not None else "absent",
                requests=1,
                detail=f"HTTP {reply.status}",
            )
        )
