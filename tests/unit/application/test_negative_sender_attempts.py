"""Intenção `rejection-attempt:` no diário de mutações do `NegativeSender` (ADR 0101)."""

from dataclasses import dataclass
from typing import cast

import pytest

from harness_dast.application.account_session import AccountSession
from harness_dast.application.dispatcher import OperationDispatcher, SendOutcome
from harness_dast.application.negative_sender import NegativeSender, NegativeSettings
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.knowledge_mutation import mutation_key
from harness_dast.domain.probe_exchange import ExchangeRecord
from tests.fakes.mutation_journal import MemoryMutationJournal

EXCHANGE = ExchangeRecord(
    operation_id="otp",
    method="POST",
    path="/auth/otp",
    target="/auth/otp",
    account="user_a",
    status=0,
    content_type="application/json",
    body='{"otp":"0000"}',
)


@dataclass
class FakeDispatcher:
    status: int

    def send(
        self,
        request: HttpRequest,
        session: object,
        *,
        allow_reauth: bool = True,
        max_attempts: int | None = None,
    ) -> SendOutcome:
        return SendOutcome(HttpResponse(status=self.status), None, 1)


class NoSessions(SessionPool):
    """Conjunto que não abre conta: o despachante falso não usa a sessão."""

    def get(self, alias: str) -> AccountSession:
        return cast(AccountSession, None)  # cast: o despachante falso ignora a sessão


def sender(
    status: int, journal: MemoryMutationJournal, *, attempts: bool, prefix: str = "rate:"
) -> NegativeSender:
    # O dublê só cumpre o que o emissor usa do despachante e do conjunto de sessões.
    dispatcher = cast(OperationDispatcher, FakeDispatcher(status))
    sessions = NoSessions(lambda alias: cast(AccountSession, None))
    return NegativeSender(
        NegativeSettings(
            base_url="http://alvo",
            dispatcher=dispatcher,
            sessions=sessions,
            product="loja",
            mutation_journal=journal,
            prefix=prefix,
            rejection_attempts=attempts,
        )
    )


def send(
    status: int, *, attempts: bool, exchange: ExchangeRecord = EXCHANGE
) -> MemoryMutationJournal:
    journal = MemoryMutationJournal()
    sender(status, journal, attempts=attempts).send(exchange, exchange.target, exchange.body)
    return journal


def test_a_500_with_rejection_attempts_is_observed_and_released() -> None:
    journal = send(500, attempts=True)

    assert journal.outcomes == ["observed"]
    assert journal.pending == set()


def test_a_500_without_rejection_attempts_stays_pending() -> None:
    journal = send(500, attempts=False)

    assert journal.outcomes == []
    assert len(journal.pending) == 1


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_transport_failure_stays_pending_even_with_rejection_attempts(status: int) -> None:
    journal = send(status, attempts=True)

    assert journal.outcomes == []
    assert len(journal.pending) == 1


def test_a_4xx_is_observed_with_or_without_rejection_attempts() -> None:
    assert send(401, attempts=True).outcomes == ["observed"]
    assert send(401, attempts=False).outcomes == ["observed"]


def test_the_rejection_attempt_key_has_its_own_prefix() -> None:
    journal = send(401, attempts=True)

    expected = mutation_key("loja", "rejection-attempt:otp", "user_a", "POST")
    assert journal.began == [expected]


def test_other_intentions_keep_the_plain_operation_key() -> None:
    journal = send(401, attempts=False)

    assert journal.began == [mutation_key("loja", "otp", "user_a", "POST")]
    assert journal.began != [mutation_key("loja", "rejection-attempt:otp", "user_a", "POST")]


def test_a_second_send_after_a_pending_5xx_is_blocked() -> None:
    journal = MemoryMutationJournal()
    plain = sender(500, journal, attempts=False)
    plain.send(EXCHANGE, EXCHANGE.target, EXCHANGE.body)

    with pytest.raises(Exception, match="pendente"):
        plain.send(EXCHANGE, EXCHANGE.target, EXCHANGE.body)


def test_a_2xx_to_a_wrong_value_is_recorded_as_a_possible_state_change() -> None:
    assert send(200, attempts=True).outcomes == ["succeeded"]
    assert send(200, attempts=False).outcomes == ["observed"]
