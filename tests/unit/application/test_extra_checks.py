"""`RateChecks` e `InventoryChecks` com emissor falso: paradas, recusas e vereditos (ADR 0101)."""

from collections.abc import Callable

from harness_dast.application.authz.sender import Reply, StopRun
from harness_dast.application.extra_checks import (
    RATE_MAX_REQUESTS,
    InventoryChecks,
    RateChecks,
)
from harness_dast.domain.extra_check_result import ExtraSkip
from harness_dast.domain.inventory_checks import InventoryPlan, SiblingFamily
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.rate_attempts import (
    ATTEMPTS_PER_OPERATION,
    AttemptCase,
    AttemptPlan,
)
from harness_dast.domain.rate_page import PagePlan

CASE = AttemptCase("otp", "/auth/otp", "otp", '{"otp":"hdas"}')
NO_PAGES = PagePlan(cases=(), skipped=())


class ScriptedSender:
    """Emissor falso: cada chamada recebe a resposta do roteiro (ou levanta a parada)."""

    def __init__(self, script: Callable[[int], Reply | Exception]) -> None:
        self._script = script
        self.sent = 0

    def send(
        self, exchange: ExchangeRecord, target: str, body: str | None, *, tag: str = ""
    ) -> Reply:
        self.sent += 1
        result = self._script(self.sent)
        if isinstance(result, Exception):
            raise result
        return result


def _attempts(script: Callable[[int], Reply | Exception]) -> tuple[ScriptedSender, RateChecks]:
    sender = ScriptedSender(script)
    return sender, RateChecks(sender, base_url="http://crapi", account="user_a")


def _run(checks: RateChecks) -> tuple[str, int, str | None]:
    summary, alerts = checks.run(NO_PAGES, AttemptPlan(cases=(CASE,), skipped=()))
    first = summary.results[0] if summary.results else None
    return (first.outcome if first else "none", len(alerts), summary.note)


def test_twenty_identical_rejections_are_a_finding_and_the_twenty_first_is_never_sent() -> None:
    sender, checks = _attempts(lambda n: Reply(401))

    outcome, alerts, _ = _run(checks)

    assert (outcome, alerts, sender.sent) == ("finding", 1, ATTEMPTS_PER_OPERATION)


def test_a_status_change_after_some_attempts_is_a_limit_and_stops_there() -> None:
    sender, checks = _attempts(lambda n: Reply(500) if n < 6 else Reply(503))

    outcome, alerts, _ = _run(checks)

    assert (outcome, alerts, sender.sent) == ("limited", 0, 6)


def test_retry_after_alone_is_a_limit_signal() -> None:
    sender, checks = _attempts(lambda n: Reply(401, retry_after="5") if n == 2 else Reply(401))

    assert _run(checks)[0] == "limited"
    assert sender.sent == 2


def test_an_unexpected_success_stops_at_once_without_a_finding() -> None:
    sender, checks = _attempts(lambda n: Reply(200))

    assert _run(checks)[:2] == ("inconclusive", 0)
    assert sender.sent == 1


def test_a_missing_route_is_inconclusive_and_not_repeated() -> None:
    sender, checks = _attempts(lambda n: Reply(404))

    assert _run(checks)[:2] == ("inconclusive", 0)
    assert sender.sent == 1


def test_a_scope_refusal_is_recorded_and_stops_the_operation() -> None:
    sender, checks = _attempts(lambda n: Reply(None, problem="scope"))

    assert _run(checks)[:2] == ("inconclusive", 0)
    assert sender.sent == 1


def test_a_run_stop_becomes_a_note_and_keeps_what_was_concluded() -> None:
    stop = StopRun("stopped_target_unresponsive", "alvo sem resposta")
    sender, checks = _attempts(lambda n: Reply(401) if n < 4 else stop)

    summary, alerts = checks.run(NO_PAGES, AttemptPlan(cases=(CASE,), skipped=()))

    assert alerts == ()
    assert summary.note is not None
    assert "alvo sem resposta" in summary.note
    assert sender.sent == 4


def test_the_summary_reports_the_cap_and_the_skipped_ones() -> None:
    skipped = ExtraSkip(subject="x", reason="no_test_identity")
    _, checks = _attempts(lambda n: Reply(401))

    summary, _ = checks.run(NO_PAGES, AttemptPlan(cases=(), skipped=(skipped,)))

    assert (summary.cap, summary.sent, summary.skipped) == (RATE_MAX_REQUESTS, 0, (skipped,))


def test_inventory_stops_on_a_run_stop_and_records_a_note() -> None:
    sender = ScriptedSender(lambda n: Reply(404) if n == 1 else StopRun("stopped_window", "janela"))
    checks = InventoryChecks(sender, base_url="http://crapi", account="user_a")
    family = SiblingFamily("v3", "/a/v999/x", ("/a/v2/x",))

    summary, alerts = checks.run(InventoryPlan((family,), ("/docs",), ()))

    assert alerts == ()
    assert summary.note is not None
    assert summary.sent == 2


def test_inventory_family_with_a_refused_control_is_skipped_not_judged() -> None:
    sender = ScriptedSender(lambda n: Reply(None, problem="scope"))
    checks = InventoryChecks(sender, base_url="http://crapi", account="user_a")
    family = SiblingFamily("v3", "/a/v999/x", ("/a/v2/x",))

    summary, _ = checks.run(InventoryPlan((family,), (), ()))

    assert [s.reason for s in summary.skipped] == ["refused_scope"]
    assert sender.sent == 1
