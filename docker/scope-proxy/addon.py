"""Cola entre o mitmproxy e a lógica do proxy de escopo (`harness_dast.adapters.scope_proxy`).

Este arquivo só traduz eventos do mitmproxy em chamadas ao `ScopeProxyEngine`; nenhuma regra
de escopo mora aqui. Roda apenas dentro da imagem do proxy (o mitmproxy não é dependência da
CLI). Falha fechado: sem política válida o módulo nem termina de carregar e o proxy não sobe.

Variáveis de ambiente: HDAST_POLICY_FILE (padrão /policy/policy.json) e HDAST_AUDIT_FILE
(padrão /audit/audit.jsonl).
"""

import asyncio
import ipaddress
import os
import socket
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from mitmproxy import ctx, exceptions, http
from mitmproxy.addonmanager import Loader
from mitmproxy.proxy.server_hooks import ServerConnectionHookData

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, Verdict, deny
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.grant_queue import GrantQueue
from harness_dast.adapters.scope_proxy.policy import load_policy
from harness_dast.adapters.scope_proxy.signals import SignalReading, read_response_signals
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.retry_after import retry_after_seconds

_REASON_HEADER = "X-Hdast-Reason"
_ERROR_MARKER = "scope-proxy:"
_STARTED = "hdast_started"
_RELEASED = "hdast_released"
_RELEASED_MONO = "hdast_released_monotonic"
_RESPONSE_MONO = "hdast_response_monotonic"
_WAITED = "hdast_waited_ms"
_AUDITED = "hdast_audited"

# Opções que, em outro valor, abririam um caminho que o proxy não inspeciona.
_REQUIRED_OPTIONS: dict[str, object] = {
    "rawtcp": False,  # TCP cru não tem URL nem método para conferir
    "http2": False,  # o proxy só inspeciona HTTP/1.1 (ver README, limitações)
    "connection_strategy": "lazy",  # só abre a conexão de saída depois de decidir
    "ignore_hosts": [],  # "ignorar" um host o deixaria passar sem interceptação
    "allow_hosts": [],
    "tcp_hosts": [],
    "udp_hosts": [],
}


class ScopeProxyAddon:
    """Liga os hooks do mitmproxy ao motor de política."""

    def __init__(self, engine: ScopeProxyEngine) -> None:
        """Guarda o motor, já construído com política válida."""
        self._engine = engine
        self._grant_queue = GrantQueue(engine, sleep=asyncio.sleep)

    def load(self, loader: Loader) -> None:
        """Aplica a política de TLS: só a política decide se o certificado é verificado."""
        ctx.options.update(ssl_insecure=not self._engine.tls_verify_upstream)

    def configure(self, updated: set[str]) -> None:
        """Recusa iniciar se uma opção insegura estiver ligada."""
        for name, expected in _REQUIRED_OPTIONS.items():
            if name in updated and getattr(ctx.options, name) != expected:
                raise exceptions.OptionsError(
                    f"scope-proxy: a opção {name} deve ser {expected!r} (falha fechada)."
                )

    # ------------------------------------------------------------- CONNECT
    def http_connect(self, flow: http.HTTPFlow) -> None:
        """Decide o túnel por host e porta; o conteúdo é decidido depois, em cada requisição."""
        verdict = self._engine.check_connect(flow.request.host, flow.request.port)
        self._log(flow, verdict, scheme="https", status=None if verdict.allowed else 403)
        if not verdict.allowed:
            flow.response = _refusal(403, verdict.reason)

    # ----------------------------------------------------------- requisição
    async def requestheaders(self, flow: http.HTTPFlow) -> None:
        """Decide a requisição (escopo completo), atrasa pela taxa e reconfere a trava."""
        request = flow.request
        if request.method == "CONNECT":
            self.http_connect(flow)
            return
        flow.metadata[_STARTED] = time.monotonic()
        verdict = self._engine.check_request(
            method=request.method,
            url=request.url,
            host_header=request.headers.get("Host"),
            wants_upgrade=_wants_upgrade(request),
        )
        if verdict.allowed:
            verdict = await self._wait_for_slot(flow)
        if not verdict.allowed:
            status = 429 if verdict.reason in (Reason.RATE_QUEUE_FULL, Reason.RATE_BACKOFF) else 403
            self._log(flow, verdict, status=status)
            flow.metadata[_AUDITED] = True
            flow.response = _refusal(status, verdict.reason, retry_after=verdict.retry_after)
            return
        flow.metadata[_RELEASED] = self._engine.now()
        flow.metadata[_RELEASED_MONO] = time.monotonic()

    async def _wait_for_slot(self, flow: http.HTTPFlow) -> Verdict:
        started = time.monotonic()
        try:
            return await self._grant_queue.acquire()
        finally:
            flow.metadata[_WAITED] = max(0, int((time.monotonic() - started) * 1000))

    # ------------------------------------------------------------- conexão
    async def server_connect(self, data: ServerConnectionHookData) -> None:
        """Resolve o nome, confere os endereços e FIXA o IP conferido na conexão.

        Fixar o IP fecha a janela entre "conferir" e "conectar" (DNS rebinding). Em TLS, o SNI
        e a verificação do certificado continuam usando o nome original.
        """
        if data.server.address is None:
            return
        host, port = data.server.address[0], data.server.address[1]
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError:
            data.server.error = f"{_ERROR_MARKER}{Reason.DNS_FAILURE.value}"
            return
        addresses = [str(info[4][0]) for info in infos]
        verdict = self._engine.check_destination(host, port, addresses)
        if not verdict.allowed:
            data.server.error = f"{_ERROR_MARKER}{verdict.reason.value}"
            return
        if not _is_ip(host):
            data.server.sni = data.server.sni or data.client.sni or host
        data.server.address = (addresses[0], port)

    # ------------------------------------------------------------- resposta
    def response(self, flow: http.HTTPFlow) -> None:
        """Registra a requisição liberada com status, bytes, duração e os sinais de erro interno."""
        if flow.metadata.get(_AUDITED) or flow.response is None:
            return
        flow.metadata[_RESPONSE_MONO] = time.monotonic()
        # Uma conexão por requisição entre o ZAP e este proxy. Como o endereço da conexão de saída
        # é o IP conferido (não dá para devolver o nome numa conexão aberta), nenhuma conexão de
        # saída é reaproveitada, e o ZAP, ao reaproveitar a de entrada, travava na sexta
        # requisição (medido no laboratório: 20 s e `Failed to read` no log do ZAP).
        flow.response.headers["Connection"] = "close"
        if flow.response.status_code == 429:
            delay = retry_after_seconds(
                flow.response.headers.get("Retry-After"), self._engine.now()
            )
            self._grant_queue.defer(delay if delay is not None else 1.0)
        body = flow.response.raw_content
        size = len(body) if body is not None else None
        # ADR 0049: a leitura só OBSERVA (conta categorias, nunca nega nem grava corpo) e falha
        # aberta: `read_response_signals` não levanta, e a linha de auditoria sai de qualquer jeito.
        reading = read_response_signals(
            flow.request.method, flow.response.status_code, flow.response.headers, body
        )
        self._log(flow, ALLOW, status=flow.response.status_code, size=size, reading=reading)

    def error(self, flow: http.HTTPFlow) -> None:
        """Registra falha do lado do destino (inclui recusa por endereço resolvido)."""
        if flow.metadata.get(_AUDITED) or flow.request.method == "CONNECT":
            return
        message = flow.error.msg if flow.error is not None else ""
        if _ERROR_MARKER in message:
            code = message.split(_ERROR_MARKER, 1)[1].strip()
            self._log(flow, deny(_reason_from(code)), status=502)
        elif flow.metadata.get(_RELEASED) is not None:
            # Sem resposta do alvo não há corpo a ler: conta como "empty" para a conta fechar.
            self._log(
                flow,
                Verdict(allowed=True, reason=Reason.UPSTREAM_ERROR),
                status=502,
                reading=SignalReading(skipped="empty"),
            )

    # --------------------------------------------------------------- apoio
    def _log(
        self,
        flow: http.HTTPFlow,
        verdict: Verdict,
        *,
        scheme: str | None = None,
        status: int | None = None,
        size: int | None = None,
        reading: SignalReading | None = None,
    ) -> None:
        request = flow.request
        started = flow.metadata.get(_STARTED)
        waited = int(flow.metadata.get(_WAITED, 0))
        duration = (
            None if started is None else max(0, int((time.monotonic() - started) * 1000) - waited)
        )
        released = flow.metadata.get(_RELEASED_MONO)
        ended = flow.metadata.get(_RESPONSE_MONO, time.monotonic())
        network = None if released is None else max(0, int((ended - released) * 1000))
        raw_path, _, raw_query = request.path.partition("?")
        self._engine.log(
            method=request.method,
            url=request.url,
            scheme=scheme or request.scheme,
            at=flow.metadata.get(_RELEASED) or self._engine.now(),
            host=request.host,
            port=request.port,
            raw_path=raw_path,
            raw_query=raw_query,
            verdict=verdict,
            status=status,
            size=size,
            duration_ms=duration,
            waited_ms=waited,
            network_ms=network,
            grant_wait_ms=flow.metadata.get(_WAITED),
            signals=reading.categories if reading else (),
            signal_skip=reading.skipped if reading else None,
        )


def _reason_from(code: str) -> Reason:
    try:
        return Reason(code)
    except ValueError:
        return Reason.ADDRESS_FORBIDDEN


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _wants_upgrade(request: http.Request) -> bool:
    # WebSocket e h2c são trocas de protocolo que o proxy não inspeciona: recusadas.
    return (
        "Upgrade" in request.headers or "upgrade" in request.headers.get("Connection", "").lower()
    )


def _refusal(status: int, reason: Reason, *, retry_after: int | None = None) -> http.Response:
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        _REASON_HEADER: reason.value,
        "Connection": "close",
    }
    if status == 429:
        headers["Retry-After"] = str(retry_after if retry_after is not None else 1)
    return http.Response.make(status, b"hdast scope-proxy: request refused\n", headers)


def _build_addon() -> ScopeProxyAddon:
    policy_file = Path(os.environ.get("HDAST_POLICY_FILE", "/policy/policy.json"))
    audit_file = Path(os.environ.get("HDAST_AUDIT_FILE", "/audit/audit.jsonl"))
    try:
        policy = load_policy(policy_file)
        # Aberto sem `with`: o arquivo vive tanto quanto o processo do proxy.
        handle = audit_file.open("a", encoding="utf-8")
    except (ConfigError, OSError) as error:
        sys.stderr.write(f"scope-proxy: RECUSANDO INICIAR. {error}\n")
        raise SystemExit(3) from None
    engine = ScopeProxyEngine(
        policy,
        policy_dir=policy_file.parent,
        audit_file=handle,
        stdout=sys.stdout,
        now=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
    )
    return ScopeProxyAddon(engine)


addons = [_build_addon()]
