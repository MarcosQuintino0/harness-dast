"""Regra pura do retrato da vigia: conceder, reverificar ou travar."""

import pytest

from harness_dast.adapters.scope_proxy.gate_watch_rule import SnapshotAction, judge_snapshot
from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause

MAX_AGE = 0.2


@pytest.mark.parametrize(
    ("stopped", "started_at", "now", "action", "cause"),
    [
        (False, 0.0, 0.0, SnapshotAction.GRANT, None),
        (False, 0.0, 0.2, SnapshotAction.GRANT, None),
        (False, 0.0, 0.201, SnapshotAction.REVERIFY, None),
        (False, 0.0, 99.0, SnapshotAction.REVERIFY, None),
        (False, 1.0, 0.5, SnapshotAction.LATCH, WatchCause.CLOCK),
        (False, None, 0.0, SnapshotAction.LATCH, WatchCause.NO_SNAPSHOT),
        (True, 0.0, 0.0, SnapshotAction.LATCH, WatchCause.CLOSE),
        (True, 0.0, 99.0, SnapshotAction.LATCH, WatchCause.CLOSE),
    ],
)
def test_julgamento_do_retrato_segue_a_tabela(
    stopped: bool,
    started_at: float | None,
    now: float,
    action: SnapshotAction,
    cause: WatchCause | None,
) -> None:
    judgement = judge_snapshot(stopped=stopped, started_at=started_at, now=now, max_age=MAX_AGE)

    assert judgement.action is action
    assert judgement.cause is cause
