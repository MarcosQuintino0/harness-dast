"""Concessões após atraso do escalonador nunca acumulam crédito para rajadas."""

import asyncio
from pathlib import Path

from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from tests.unit.adapters.scope_proxy.test_engine import Rig


def test_atraso_no_escalonador_nao_antecipa_proxima_concessao(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.engine.grant_slot()
    waits: list[float] = []

    async def delayed_sleep(delay: float) -> None:
        waits.append(delay)
        rig.clocks.mono += delay + 10

    async def scenario() -> None:
        queue = GrantQueue(rig.engine, sleep=delayed_sleep)
        assert (await queue.acquire()).allowed
        assert (await queue.acquire()).allowed

    asyncio.run(scenario())
    assert len(waits) == 2
    assert waits[1] > 0
