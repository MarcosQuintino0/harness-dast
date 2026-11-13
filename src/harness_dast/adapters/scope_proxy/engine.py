"""Motor do proxy: reúne política, decisão, endereço, taxa, trava e auditoria.

É a única superfície que a cola do mitmproxy (`docker/scope-proxy/addon.py`) usa. O que
garante: nenhuma requisição é liberada sem passar, nesta ordem, por trava/prazo, recusa de
upgrade, coerência do cabeçalho `Host`, `ScopeGuard` e, ao conectar, endereço resolvido;
toda recusa e toda requisição liberada geram um registro de auditoria. O que não faz:
não fala HTTP nem dorme; quem chama executa a espera devolvida por `reserve_slot`.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from harness_dast.adapters.scope_proxy.addresses import check_addresses
from harness_dast.adapters.scope_proxy.audit import AuditLog, AuditRecord, describe_target
from harness_dast.adapters.scope_proxy.decision import (
    Reason,
    ScopeDecider,
    Verdict,
    deny,
)
from harness_dast.adapters.scope_proxy.gate import RunGate
from harness_dast.adapters.scope_proxy.policy import KILL_FLAG_NAME, ProxyPolicy, deadline_of
from harness_dast.adapters.scope_proxy.ratelimit import RateLimiter
from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.host import parse_host
from harness_dast.domain.urlnorm import default_port, normalize_request


class ScopeProxyEngine:
    """Aplica a política de uma execução a cada requisição que o mitmproxy vê."""

    def __init__(
        self,
        policy: ProxyPolicy,
        *,
        policy_dir: Path,
        audit_file: TextIO,
        stdout: TextIO,
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> None:
        """Monta o motor.

        Args:
            policy: Política validada.
            policy_dir: Diretório da política; o arquivo `KILL` dentro dele aciona a trava.
            audit_file: Arquivo de auditoria aberto para acréscimo.
            stdout: Saída padrão, que recebe as mesmas linhas.
            now: Relógio com fuso (injetado).
            monotonic: Relógio monotônico (injetado).
        """
        self._policy = policy
        self._now = now
        self._decider = ScopeDecider(policy.scope)
        self._gate = RunGate(
            kill_flag=policy_dir / KILL_FLAG_NAME,
            deadline=deadline_of(policy, now()),
            now=now,
        )
        self._limiter = RateLimiter(
            requests_per_second=policy.limits.requests_per_second,
            max_queued=policy.max_queued_requests,
            monotonic=monotonic,
        )
        self._audit = AuditLog(
            file=audit_file, stdout=stdout, on_failure=self._gate.mark_audit_failure
        )

    def now(self) -> datetime:
        """Instante atual, para a cola carimbar o momento em que um pedido foi liberado."""
        return self._now()

    @property
    def tls_verify_upstream(self) -> bool:
        """Se o certificado do servidor de destino deve ser verificado."""
        return self._policy.tls_verify_upstream

    def check_connect(self, host: str, port: int) -> Verdict:
        """Decide um túnel `CONNECT`: trava/prazo e depois host, `https` e porta."""
        gate = self._gate.check()
        return gate if not gate.allowed else self._decider.decide_connect(host, port)

    def check_request(
        self, *, method: str, url: str, host_header: str | None, wants_upgrade: bool
    ) -> Verdict:
        """Decide uma requisição já com o destino real da conexão em `url`."""
        gate = self._gate.check()
        if not gate.allowed:
            return gate
        if wants_upgrade:
            return deny(Reason.UPGRADE_REFUSED)
        verdict = self._decider.decide_request(method, url)
        # Depois do ScopeGuard: assim a URL malformada recebe o motivo certo e o cabeçalho
        # Host só é conferido para o que já está dentro do escopo.
        if verdict.allowed and not _host_header_matches(host_header, url):
            return deny(Reason.HOST_HEADER_MISMATCH)
        return verdict

    def recheck_after_wait(self) -> Verdict:
        """Reconfere trava e prazo depois da espera na fila (podem ter mudado)."""
        return self._gate.check()

    def reserve_slot(self) -> float | None:
        """Reserva horário de saída; `None` significa fila cheia (recusar com 429)."""
        return self._limiter.reserve()

    def check_destination(self, host: str, port: int, addresses: list[str]) -> Verdict:
        """Confere os endereços que o DNS devolveu para `host`, antes de conectar."""
        return check_addresses(addresses, allow_local=self._local_allowed(host, port))

    def log(
        self,
        *,
        method: str,
        url: str,
        scheme: str,
        at: datetime,
        host: str,
        port: int,
        raw_path: str,
        raw_query: str,
        verdict: Verdict,
        status: int | None = None,
        size: int | None = None,
        duration_ms: int | None = None,
        waited_ms: int = 0,
    ) -> None:
        """Grava uma linha de auditoria (consulta reduzida aos nomes dos parâmetros)."""
        path, names = describe_target(method, url, raw_path, raw_query)
        self._audit.write(
            AuditRecord(
                ts=at.astimezone(UTC).isoformat(timespec="milliseconds"),
                run_id=self._policy.run_id,
                method=method,
                scheme=scheme,
                host=host,
                port=port,
                path=path,
                query_params=tuple(names),
                decision="allow" if verdict.allowed else "deny",
                reason=verdict.reason.value,
                status=status,
                bytes=size,
                duration_ms=duration_ms,
                waited_ms=waited_ms,
            )
        )

    def _local_allowed(self, host: str, port: int) -> bool:
        try:
            wanted = parse_host(host if ":" not in host else f"[{host}]")
        except ScopeViolation:
            return False
        return any(
            rule.allow_local
            and parse_host(rule.host) == wanted
            and (default_port(rule.scheme) if rule.port is None else rule.port) == port
            for rule in self._policy.scope.allow
        )


_HOST_HEADER = re.compile(r"(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._-]+)(?::[0-9]{1,5})?")


def _host_header_matches(host_header: str | None, url: str) -> bool:
    # O destino real é o da URL. Se o cabeçalho Host apontar para outro nome, um servidor
    # atrás de proxy reverso roteia pelo cabeçalho e a requisição sairia do escopo.
    # Só `host[:porta]` é um Host válido; `host/x`, `host?x` e `host#...` seriam lidos como URL por
    # esta função, mas um servidor os interpretaria de outro jeito.
    if not host_header or _HOST_HEADER.fullmatch(host_header) is None:
        return False
    try:
        target = normalize_request("GET", url)
        claimed = normalize_request("GET", f"{target.scheme}://{host_header}/")
    except ScopeViolation:
        return False
    return claimed.host == target.host and claimed.port == target.port
