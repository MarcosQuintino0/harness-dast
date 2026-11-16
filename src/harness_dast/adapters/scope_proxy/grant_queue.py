"""Serializa concessões reais sem acumular crédito quando o escalonador atrasa."""

import asyncio
import math
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
        self._backoff_changed = asyncio.Event()

    def defer(self, seconds: float) -> None:
        """Adia concessões e desperta quem já aguardava a taxa."""
        self._engine.defer_slots(seconds)
        self._backoff_changed.set()

    async def acquire(self) -> Verdict:
        """Espera e concede, ou devolve a recusa; cancelamento não deixa vaga ocupada."""
        verdict = self._check_backoff()
        if verdict is not None:
            return verdict
        if self._waiting >= self._engine.max_queued_requests:
            return deny(Reason.RATE_QUEUE_FULL)
        self._waiting += 1
        try:
            async with self._lock:
                while True:
                    backoff = self._check_backoff()
                    if backoff is not None:
                        return backoff
                    self._backoff_changed.clear()
                    delay = self._engine.grant_delay()
                    if delay <= 0:
                        self._engine.grant_slot()
                        return ALLOW
                    await self._wait_or_backoff(delay)
        finally:
            self._waiting -= 1

    def _check_backoff(self) -> Verdict | None:
        # A trava e o prazo têm prioridade sobre uma recusa temporária.
        verdict = self._engine.recheck_after_wait()
        if not verdict.allowed:
            return verdict
        remaining = self._engine.backoff_remaining()
        if remaining > 0:
            return Verdict(False, Reason.RATE_BACKOFF, retry_after=math.ceil(remaining))
        return None

    async def _wait_or_backoff(self, delay: float) -> None:
        sleeper = asyncio.ensure_future(self._sleep(delay))
        changed = asyncio.create_task(self._backoff_changed.wait())
        try:
            await asyncio.wait((sleeper, changed), return_when=asyncio.FIRST_COMPLETED)
            if sleeper.done():
                sleeper.result()
        finally:
            sleeper.cancel()
            changed.cancel()
            await asyncio.gather(sleeper, changed, return_exceptions=True)
