"""SSRF guiado pelo contrato: envia a URL de retorno e confere o que voltou (ADR 0100).

Cada pedido sai pelo MESMO caminho do `negative` (`NegativeSender` sobre `OperationDispatcher` e
`GuardedSender`: escopo, `deny_paths`, métodos, taxa, janela, prazo, trava, auditoria e diário de
mutações); a auditoria o identifica pelo prefixo `oast:`. Nada aqui decide escopo, teto ou
correlação: isso é do domínio (`domain.oast_ssrf`). O corpo da resposta nunca é guardado.
"""

from dataclasses import dataclass
from typing import Final, Protocol

from harness_dast.application.authz.sender import Reply, StopRun
from harness_dast.application.common_ports import Sleeper
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.scan_ports import OastEvents
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.knowledge_mutation import MutationPending
from harness_dast.domain.oast_ssrf import (
    SSRF_MAX_REQUESTS,
    OastEvent,
    SsrfCase,
    SsrfPlan,
    SsrfSkip,
    SsrfSummary,
    correlate,
    observation_alert,
    render_case,
)
from harness_dast.domain.probe_exchange import ExchangeRecord

OAST_PREFIX: Final = "oast:"
"""Prefixo do `operation_id` na auditoria dos pedidos do SSRF guiado."""

WAIT_SECONDS: Final = 10.0
"""Quanto se espera o retorno depois do último pedido (o alvo pode chamar de forma assíncrona)."""

_POLL_SECONDS: Final = 1.0


class SsrfSender(Protocol):
    """Emissor dos pedidos (na prática o `NegativeSender` com o prefixo `oast:`)."""

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
class SsrfOutcome:
    """Resultado da etapa.

    Attributes:
        summary: Resumo para o `scan.json`.
        alerts: Alertas no formato do ZAP, um por retorno correlacionado.
        observable: Se o observador permaneceu disponível durante a etapa.
    """

    summary: SsrfSummary
    alerts: tuple[dict[str, str], ...]
    observable: bool = True


class GuidedSsrf:
    """Envia os pedidos do plano e correlaciona os retornos."""

    def __init__(
        self, *, sender: SsrfSender, events: OastEvents, sleeper: Sleeper, base_url: str
    ) -> None:
        """Cria a etapa.

        Args:
            sender: Emissor do estágio (prefixo `oast:`).
            events: Porta dos eventos do serviço de retorno.
            sleeper: Espera entre as consultas.
            base_url: URL base do ambiente.
        """
        self._sender = sender
        self._events = events
        self._sleeper = sleeper
        self._base_url = base_url

    def run(self, plan: SsrfPlan) -> SsrfOutcome:
        """Envia o plano e devolve o que voltou.

        Sem pedido a enviar não toca o ZAP. Se o ZAP não responde ao ponto de partida, nada é
        enviado (sem como observar, não se induz o alvo a chamar ninguém).
        """
        if not plan.cases:
            return SsrfOutcome(SsrfSummary(enabled=True, skipped=plan.skipped), ())
        try:
            baseline = self._events.oast_baseline()
        except ExternalToolError as error:
            skipped = (
                *plan.skipped,
                *(
                    SsrfSkip(operation_id=c.operation_id, field=c.field, reason="oast_unavailable")
                    for c in plan.cases
                ),
            )
            note = f"Serviço de retorno indisponível; nada foi enviado: {error.message}"
            return SsrfOutcome(SsrfSummary(enabled=True, skipped=skipped, note=note), (), False)
        sent_cases: list[SsrfCase] = []
        statuses: dict[str, int | None] = {}
        refused: list[SsrfSkip] = []
        stopped: str | None = None
        for case in plan.cases:
            target, body = render_case(case)
            try:
                reply = self._sender.send(case.exchange, target, body, tag="")
            except MutationPending:
                refused.append(
                    SsrfSkip(
                        operation_id=case.operation_id, field=case.field, reason="mutation_pending"
                    )
                )
                continue
            except (StopRun, WindowClosed, DeadlineReached, ExternalToolError) as stop:
                stopped = f"A etapa parou antes de terminar: {stop}"
                break
            if reply.problem is not None:
                refused.append(
                    SsrfSkip(
                        operation_id=case.operation_id,
                        field=case.field,
                        reason=f"refused_{reply.problem}",
                    )
                )
                continue
            sent_cases.append(case)
            statuses[case.token] = reply.status
        seen, wait_note = self._wait(sent_cases, baseline)
        observations = correlate(sent_cases, statuses, seen, base_url=self._base_url)
        summary = SsrfSummary(
            enabled=True,
            planned=len(plan.cases),
            sent=self._sender.sent,
            observed=len(observations),
            events_seen=len(seen),
            cap=SSRF_MAX_REQUESTS,
            observations=observations,
            skipped=(*plan.skipped, *refused),
            note=stopped or wait_note,
        )
        alerts = tuple(
            observation_alert(index, item, base_url=self._base_url)
            for index, item in enumerate(observations, start=1)
        )
        return SsrfOutcome(summary, alerts, wait_note is None)

    def _wait(
        self, cases: list[SsrfCase], baseline: int
    ) -> tuple[tuple[OastEvent, ...], str | None]:
        """Consulta o serviço de retorno até todos os tokens voltarem ou o tempo acabar."""
        wanted = {case.token for case in cases}
        seen: tuple[OastEvent, ...] = ()
        waited = 0.0
        while wanted:
            try:
                seen = self._events.oast_events(baseline)
            except ExternalToolError as error:
                return seen, f"Não foi possível ler os eventos do retorno: {error.message}"
            if wanted <= {event.path.strip("/") for event in seen} or waited >= WAIT_SECONDS:
                break
            self._sleeper.sleep(_POLL_SECONDS)
            waited += _POLL_SECONDS
        return seen, None
