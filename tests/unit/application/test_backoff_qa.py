"""Reproduz a colisão entre Retry-After, espera do proxy e timeout do cliente."""

import asyncio
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness_dast.adapters.http.target_client import TargetClientSettings
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.errors import TargetTimeout
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.retry_after import retry_after_seconds
from tests.fakes.probe_ports import reply
from tests.fakes.rig import TOKEN, Rig, operation
from tests.unit.adapters.scope_proxy.helpers import make_policy


def test_recuo_do_proxy_nao_deve_parecer_timeout_do_alvo(tmp_path: Path) -> None:
    """Um 429 válido seguido de espera interna não pode virar falsa falha de transporte."""
    upstream_times: list[float] = []
    deadline = 0.0
    timeout = TargetClientSettings(zap_proxy_url="http://proxy-local").timeout_seconds

    async def sleep(seconds: float) -> None:
        if seconds > timeout:
            rig.clock.advance(timeout)
            raise TargetTimeout("proxy ainda aguarda concessão")
        rig.clock.advance(seconds)

    def handler(request: HttpRequest, _jar: dict[str, str]) -> Any:
        nonlocal deadline
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        try:
            verdict = runner.run(queue.acquire())
        except TargetTimeout as error:
            return error
        if not verdict.allowed:
            assert verdict.reason == "rate_backoff"
            remaining = getattr(verdict, "retry_after", None)
            assert isinstance(remaining, int)
            assert remaining > 0
            return reply(429, {}, retry_after=str(remaining))
        now = rig.clock.now().timestamp()
        upstream_times.append(now)
        if len(upstream_times) == 1:
            delay = retry_after_seconds("58", datetime(2026, 1, 1, tzinfo=UTC))
            assert delay is not None
            deadline = now + delay
            # Antes da correção, o addon registrava o recuo no motor diretamente.
            if hasattr(queue, "defer"):
                queue.defer(delay)
            else:
                engine.defer_slots(delay)
            return reply(429, {}, retry_after="58")
        if now < deadline:
            return reply(429, {}, retry_after="1")
        return reply(200, {})

    spec = ApiSpec(title="T", version="1", operations=(operation("ler", "get", "/api/ler"),))
    rig = Rig(spec=spec, handler=handler)
    engine = ScopeProxyEngine(
        make_policy(),
        policy_dir=tmp_path,
        audit_file=io.StringIO(),
        stdout=io.StringIO(),
        now=rig.clock.now,
        monotonic=lambda: rig.clock.now().timestamp(),
    )
    queue = GrantQueue(engine, sleep=sleep)
    with asyncio.Runner() as runner:
        result = rig.probe().execute(ProbeRequest(product="agenda"))
    assert result.operations[0].outcome in {"success", "rate_limited"}
    assert upstream_times
    assert all(timestamp >= deadline for timestamp in upstream_times[1:])
