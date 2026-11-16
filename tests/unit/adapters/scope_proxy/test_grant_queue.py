"""Concessões com relógio e espera controlados, sem rede."""

import asyncio
from contextlib import suppress
from datetime import timedelta
from pathlib import Path

from harness_dast.adapters.scope_proxy.decision import Reason, Verdict
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
    assert verdict.reason is Reason.RATE_BACKOFF
    assert verdict.retry_after == 3
    assert len(waits) == 1


def test_recuo_de_60_segundos_recusa_imediato_apos_retry_de_30(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    sends: list[tuple[str, float]] = []

    async def sleep(delay: float) -> None:
        rig.clocks.mono += delay

    async def scenario() -> None:
        queue = GrantQueue(rig.engine, sleep=sleep)

        async def send(method: str) -> Verdict:
            verdict = await queue.acquire()
            if verdict.allowed:
                sends.append((method, rig.clocks.mono))
            return verdict

        assert (await send("POST")).allowed
        queue.defer(60)
        rig.clocks.mono += 30  # limite de espera do cliente
        result = await asyncio.wait_for(send("POST"), timeout=15)
        assert (result.reason, result.retry_after) == (Reason.RATE_BACKOFF, 30)
        rig.clocks.mono += 29.9
        assert (await send("POST")).retry_after == 1
        rig.clocks.mono += 0.1
        assert (await send("GET")).allowed

    asyncio.run(scenario())
    assert [method for method, _ in sends] == ["POST", "GET"]


def test_recuo_desperta_pedidos_que_aguardam_taxa(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.engine.grant_slot()

    async def scenario() -> None:
        entered = asyncio.Event()

        async def sleep(delay: float) -> None:
            entered.set()
            await asyncio.Event().wait()

        queue = GrantQueue(rig.engine, sleep=sleep)
        first = asyncio.create_task(queue.acquire())
        await entered.wait()
        second = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        queue.defer(60)
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
        assert all(result.reason is Reason.RATE_BACKOFF for result in results)
        assert all(result.retry_after == 60 for result in results)

    asyncio.run(scenario())


def test_parada_tem_prioridade_durante_recuo(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    async def scenario() -> None:
        queue = GrantQueue(rig.engine, sleep=asyncio.sleep)
        queue.defer(60)
        (tmp_path / KILL_FLAG_NAME).touch()
        assert (await queue.acquire()).reason is Reason.KILL_SWITCH

    asyncio.run(scenario())


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
