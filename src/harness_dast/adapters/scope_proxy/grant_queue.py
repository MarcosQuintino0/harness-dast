"""Serializa concessões reais sem acumular crédito quando o escalonador atrasa."""

import asyncio
from collections.abc import Awaitable, Callable

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, Verdict, deny
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine


class GrantQueue:
    """Fila limitada, com trava reconferida depois de cada suspensão."""

    def __init__(
        self, engine: ScopeProxyEngine, *, sleep: Callable[[float], Awaitable[None]]
    ) -> None:
        """Recebe motor e espera injetada para testes determinísticos."""
        self._engine = engine
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._waiting = 0

    async def acquire(self) -> Verdict:
        """Espera e concede, ou devolve a recusa; cancelamento não deixa vaga ocupada."""
        if self._waiting >= self._engine.max_queued_requests:
            return deny(Reason.RATE_QUEUE_FULL)
        self._waiting += 1
        try:
            async with self._lock:
                while True:
                    verdict = self._engine.recheck_after_wait()
                    if not verdict.allowed:
                        return verdict
                    delay = self._engine.grant_delay()
                    if delay <= 0:
                        self._engine.grant_slot()
                        return ALLOW
                    await self._sleep(delay)
        finally:
            self._waiting -= 1
