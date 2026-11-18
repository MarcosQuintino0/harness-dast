"""Regra pura do retrato da vigia: conceder, reverificar ou travar.

Fica no adaptador (e não em `domain`) porque devolve `WatchCause`, categoria do diagnóstico da
vigia, que pertence ao adaptador do proxy; a função em si não faz E/S nem lê relógio (ADR 0106).
"""

from enum import StrEnum
from typing import NamedTuple

from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause


class SnapshotAction(StrEnum):
    """O que fazer com o retrato disponível no instante da decisão."""

    GRANT = "grant"
    REVERIFY = "reverify"
    LATCH = "latch"


class SnapshotJudgement(NamedTuple):
    """Ação decidida e, quando trava, a categoria segura do motivo."""

    action: SnapshotAction
    cause: WatchCause | None = None


def judge_snapshot(
    *, stopped: bool, started_at: float | None, now: float, max_age: float
) -> SnapshotJudgement:
    """Julga o retrato sem efeito colateral.

    Garante: só `GRANT` quando o retrato existe, a vigia não foi encerrada e a idade está em
    `0 <= idade <= max_age`. Retrato velho vira `REVERIFY` (atraso não é alteração, mas nunca
    concede). Encerramento, ausência de retrato e relógio para trás sempre viram `LATCH`.
    """
    if stopped:
        return SnapshotJudgement(SnapshotAction.LATCH, WatchCause.CLOSE)
    if started_at is None:
        return SnapshotJudgement(SnapshotAction.LATCH, WatchCause.NO_SNAPSHOT)
    age = now - started_at
    if age < 0:
        return SnapshotJudgement(SnapshotAction.LATCH, WatchCause.CLOCK)
    if age > max_age:
        return SnapshotJudgement(SnapshotAction.REVERIFY)
    return SnapshotJudgement(SnapshotAction.GRANT)
