"""Concessões com relógio e espera controlados, sem rede."""

import asyncio
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from harness_dast.adapters.scope_proxy.policy import KILL_FLAG_NAME
from tests.unit.adapters.scope_proxy.test_engine import Rig


def test_reconfere_parada_apos_espera(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.engine.grant_slot()

    async def sleep(delay: float) -> None:
        rig.clocks.mono += delay
        (tmp_path / KILL_FLAG_NAME).touch()

    verdict = asyncio.run(GrantQueue(rig.engine, sleep=sleep).acquire())
    assert verdict.reason is Reason.KILL_SWITCH


def test_reconfere_prazo_apos_espera(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.engine.grant_slot()

    async def sleep(delay: float) -> None:
        rig.clocks.mono += delay
        rig.clocks.wall += timedelta(days=2)

    verdict = asyncio.run(GrantQueue(rig.engine, sleep=sleep).acquire())
    assert verdict.reason is Reason.RUN_EXPIRED


def test_recuo_posterior_a_espera_e_reavaliado(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.engine.grant_slot()
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        rig.clocks.mono += delay
        if len(waits) == 1:
            rig.engine.defer_slots(3)

    verdict = asyncio.run(GrantQueue(rig.engine, sleep=sleep).acquire())
    assert verdict.allowed
    assert len(waits) == 2
    assert waits[1] == 3


def test_cancelamento_devolve_vaga_da_fila(tmp_path: Path) -> None:
    rig = Rig(tmp_path, max_queued_requests=1)
    rig.engine.grant_slot()

    async def scenario() -> tuple[Reason, Reason]:
        entered = asyncio.Event()

        async def sleep(delay: float) -> None:
            entered.set()
            await asyncio.Event().wait()

        queue = GrantQueue(rig.engine, sleep=sleep)
        task = asyncio.create_task(queue.acquire())
        await entered.wait()
        rejected = await queue.acquire()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        rig.clocks.mono += 10
        granted = await queue.acquire()
        return rejected.reason, granted.reason

    assert asyncio.run(scenario()) == (Reason.RATE_QUEUE_FULL, Reason.ALLOWED)
