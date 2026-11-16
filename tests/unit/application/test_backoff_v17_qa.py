"""Reproduz a colisão entre Retry-After, espera do proxy e timeout do cliente."""

from datetime import UTC, datetime
from typing import Any

from harness_dast.adapters.http.target_client import TargetClientSettings
from harness_dast.adapters.scope_proxy.ratelimit import RateLimiter
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.errors import TargetTimeout
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.retry_after import retry_after_seconds
from tests.fakes.probe_ports import reply
from tests.fakes.rig import TOKEN, Rig, operation


def test_recuo_do_proxy_nao_deve_parecer_timeout_do_alvo() -> None:
    """Um 429 válido seguido de espera interna não pode virar falsa falha de transporte."""
    sent = 0
    deadline = 0.0
    timeout = TargetClientSettings(zap_proxy_url="http://proxy-local").timeout_seconds

    def handler(request: HttpRequest, _jar: dict[str, str]) -> Any:
        nonlocal sent, deadline
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        sent += 1
        now = rig.clock.now().timestamp()
        if sent == 1:
            delay = retry_after_seconds("58", datetime(2026, 1, 1, tzinfo=UTC))
            assert delay is not None
            deadline = now + delay
            proxy.defer(delay)
            return reply(429, {}, retry_after="58")
        wait = proxy.delay_until_grant()
        if wait > timeout:
            rig.clock.advance(timeout)
            return TargetTimeout("proxy ainda aguarda concessão")
        rig.clock.advance(wait)
        if rig.clock.now().timestamp() < deadline:
            return reply(429, {}, retry_after="1")
        return reply(200, {})

    spec = ApiSpec(title="T", version="1", operations=(operation("ler", "get", "/api/ler"),))
    rig = Rig(spec=spec, handler=handler)
    proxy = RateLimiter(
        requests_per_second=50, max_queued=100, monotonic=lambda: rig.clock.now().timestamp()
    )
    result = rig.probe().execute(ProbeRequest(product="agenda"))
    assert result.operations[0].outcome in {"success", "rate_limited"}
