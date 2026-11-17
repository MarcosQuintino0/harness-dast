"""`GuidedSsrf`: envio do plano, paradas e leitura do retorno, com emissor e retorno falsos."""

import json
from dataclasses import replace

from harness_dast.application.authz.sender import Reply, StopRun
from harness_dast.application.oast_ssrf import WAIT_SECONDS, GuidedSsrf, SsrfOutcome
from harness_dast.application.run_support import DeadlineReached
from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.oast_ssrf import OastEvent, SsrfPlan, plan_ssrf
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.runtime import ManualClock

BASE = "http://alvo"


def _plan(count: int = 2) -> SsrfPlan:
    fields = {f"hook_{n}_url": Schema(type="string") for n in range(count)}
    schema = Schema(type="object", properties=fields)
    operation = Operation(
        operation_id="o",
        method="post",
        path="/x",
        request_body=RequestBody(
            required=True,
            media=(MediaBody(media_type="application/json", body_schema=schema),),
        ),
    )
    exchange = ExchangeRecord(
        operation_id="o",
        method="POST",
        path="/x",
        target="/x",
        account="a",
        status=200,
        content_type="application/json",
        body=json.dumps({name: "v" for name in fields}),
    )
    return plan_ssrf([exchange], {"o": operation}, permits=lambda m, t: True, seed=1)


class FakeSender:
    """`SsrfSender` falso: responde por posição e pode parar no meio."""

    def __init__(self, replies: list[Reply | Exception]) -> None:
        self.replies = list(replies)
        self.sent = 0
        self.bodies: list[str | None] = []

    def send(
        self, exchange: ExchangeRecord, target: str, body: str | None, *, tag: str = ""
    ) -> Reply:
        self.bodies.append(body)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        if item.problem is None:
            self.sent += 1
        return item


class FakeEvents:
    """`OastEvents` falso."""

    def __init__(
        self, events: tuple[OastEvent, ...] = (), *, fail_after: int | None = None
    ) -> None:
        self.events = events
        self.fail_after = fail_after
        self.reads = 0

    def oast_baseline(self) -> int:
        return 0

    def oast_events(self, since: int) -> tuple[OastEvent, ...]:
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise ExternalToolError("ZAP caiu.")
        return self.events


def _run(
    sender: FakeSender, events: FakeEvents, plan: SsrfPlan | None = None
) -> tuple[SsrfOutcome, ManualClock]:
    clock = ManualClock()
    outcome = GuidedSsrf(sender=sender, events=events, sleeper=clock, base_url=BASE).run(
        plan or _plan()
    )
    return outcome, clock


def test_an_empty_plan_sends_nothing_and_never_touches_the_return_service() -> None:
    events = FakeEvents()

    outcome, _ = _run(FakeSender([]), events, SsrfPlan(cases=(), skipped=()))

    assert outcome.summary.enabled is True
    assert outcome.summary.planned == 0
    assert events.reads == 0


def test_a_request_refused_by_the_scope_is_recorded_and_not_waited_for() -> None:
    sender = FakeSender([Reply(None, problem="scope"), Reply(None, problem="account")])
    events = FakeEvents()

    outcome, clock = _run(sender, events)

    summary = outcome.summary
    assert [s.reason for s in summary.skipped] == ["refused_scope", "refused_account"]
    assert (summary.sent, summary.observed) == (0, 0)
    assert clock.sleeps == []


def test_a_stop_in_the_middle_keeps_what_was_sent_and_says_why() -> None:
    sender = FakeSender([Reply(200), StopRun("stopped_target_unresponsive", "alvo mudo")])

    outcome, _ = _run(sender, FakeEvents())

    summary = outcome.summary
    assert summary.sent == 1
    assert summary.note is not None
    assert "alvo mudo" in summary.note


def test_a_proxy_failure_in_the_middle_is_a_stop_note_and_does_not_abort_the_scan() -> None:
    sender = FakeSender([Reply(200), ExternalToolError("proxy do ZAP fora do ar")])

    outcome, _ = _run(sender, FakeEvents())

    assert outcome.summary.sent == 1
    assert outcome.summary.note is not None
    assert "proxy do ZAP fora do ar" in outcome.summary.note


def test_a_deadline_stops_the_stage_without_raising() -> None:
    sender = FakeSender([DeadlineReached("prazo")])

    outcome, _ = _run(sender, FakeEvents())

    assert outcome.summary.note is not None


def test_waits_up_to_the_limit_when_nothing_returns() -> None:
    events = FakeEvents()

    outcome, clock = _run(FakeSender([Reply(200), Reply(200)]), events)

    assert outcome.summary.observed == 0
    assert sum(clock.sleeps) == WAIT_SECONDS
    assert events.reads == int(WAIT_SECONDS) + 1


def test_a_failure_reading_the_events_is_a_note_not_an_error() -> None:
    outcome, _ = _run(FakeSender([Reply(200), Reply(200)]), FakeEvents(fail_after=0))

    summary = outcome.summary
    assert summary.observed == 0
    assert summary.note is not None
    assert "eventos" in summary.note


def test_ssrf_pula_conta_pendente_e_correlaciona_apenas_pedido_enviado() -> None:
    from harness_dast.domain.knowledge_mutation import mutation_key
    from tests.fakes.mutation_journal import MemoryMutationJournal
    from tests.unit.application.test_negative_sender_attempts import sender as journal_sender

    first, second = _plan().cases
    second = replace(second, exchange=second.exchange.model_copy(update={"account": "b"}))
    plan = SsrfPlan(cases=(first, second), skipped=())
    journal = MemoryMutationJournal()
    journal.begin(mutation_key("loja", first.operation_id, "a", "POST"), "unknown")
    sender = journal_sender(200, journal, attempts=False, prefix="oast:")
    events = FakeEvents(
        (OastEvent(event_id=1, path=first.token), OastEvent(event_id=2, path=second.token))
    )
    outcome = GuidedSsrf(sender=sender, events=events, sleeper=ManualClock(), base_url=BASE).run(
        plan
    )
    assert outcome.summary.sent == 1
    assert [(skip.operation_id, skip.field, skip.reason) for skip in outcome.summary.skipped] == [
        (first.operation_id, first.field, "mutation_pending")
    ]
    assert [item.token for item in outcome.summary.observations] == [second.token]
    assert len(outcome.alerts) == 1


def test_ssrf_interrompe_quando_diario_inacessivel() -> None:
    from harness_dast.application.mutation_guard import MutationJournalBlocked

    outcome, _ = _run(FakeSender([MutationJournalBlocked("diario indisponivel")]), FakeEvents())
    assert outcome.summary.sent == 0
    assert outcome.summary.observed == 0
    assert outcome.summary.note is not None
    assert "diario indisponivel" in outcome.summary.note
