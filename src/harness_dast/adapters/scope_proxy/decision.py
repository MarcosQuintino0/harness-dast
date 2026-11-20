"""Decisão por requisição: delega ao `ScopeGuard` e traduz o resultado em código estável.

O que garante: `allowed` só é verdadeiro se o `ScopeGuard` aceitou a requisição (a decisão de
escopo nunca é refeita aqui). Para o túnel `CONNECT` só confere host, esquema `https` e porta
contra as regras de permissão, pois o caminho e o método só existem dentro do túnel.
O que não faz: não resolve DNS, não olha cabeçalhos e não aplica prazo nem taxa.
"""

from dataclasses import dataclass
from enum import StrEnum

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.scope import OutboundRequest, PathMode, Scope, ScopeGuard
from harness_dast.domain.scope_reason import WIDE_READING_OUTSIDE_ALLOW
from harness_dast.domain.wide_guard import WideScopeGuard


class Reason(StrEnum):
    """Códigos de motivo estáveis; vão no cabeçalho `X-Hdast-Reason` e na auditoria."""

    ALLOWED = "allowed"
    MALFORMED_REQUEST = "malformed_request"
    DENY_PATH = "deny_path"
    HOST_NOT_ALLOWED = "host_not_allowed"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    PATH_NOT_ALLOWED = "path_not_allowed"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    HOST_HEADER_MISMATCH = "host_header_mismatch"
    UPGRADE_REFUSED = "upgrade_refused"
    ADDRESS_FORBIDDEN = "address_forbidden"
    DNS_FAILURE = "dns_failure"
    UPSTREAM_ERROR = "upstream_error"
    KILL_SWITCH = "kill_switch"
    RUN_EXPIRED = "run_expired"
    APPROVAL_CHANGED = "approval_changed"
    RATE_QUEUE_FULL = "rate_queue_full"
    RATE_BACKOFF = "rate_backoff"
    AUDIT_FAILURE = "audit_failure"


@dataclass(frozen=True, slots=True)
class Verdict:
    """Resultado de uma checagem.

    Attributes:
        allowed: `True` só quando todas as checagens aplicáveis passaram.
        reason: Código do motivo (`ALLOWED` quando permitido). Para recusa por forma da URL ou
            do caminho é sempre o agrupador `MALFORMED_REQUEST` (contrato antigo).
        detail: Código granular (`ScopeReason`) da recusa por forma, por exemplo
            `path_encoded_slash`; `WIDE_READING_OUTSIDE_ALLOW` numa liberação do modo amplo em que
            alguma leitura do caminho sai de `scope.allow`. `None` nos demais casos.
        retry_after: Segundos restantes, arredondados para cima, na recusa de recuo.
    """

    allowed: bool
    reason: Reason
    detail: str | None = None
    retry_after: int | None = None


ALLOW = Verdict(allowed=True, reason=Reason.ALLOWED)


def deny(reason: Reason, detail: str | None = None) -> Verdict:
    """Cria uma recusa com o motivo dado (e o código granular, se houver)."""
    return Verdict(allowed=False, reason=reason, detail=detail)


def classify(error: ScopeViolation) -> Reason:
    """Traduz o código de uma `ScopeViolation` no motivo do proxy.

    Violação sem código (ou de forma) vira `MALFORMED_REQUEST`; uma violação nova sem código
    só perde precisão do motivo, nunca abre acesso, porque a recusa vem da exceção.
    """
    reason = error.reason
    if reason is None or reason.is_malformed:
        return Reason.MALFORMED_REQUEST
    return Reason(reason.value)


def verdict_from(error: ScopeViolation) -> Verdict:
    """Recusa com o agrupador compatível em `reason` e o código granular em `detail`."""
    reason = error.reason
    detail = reason.value if reason is not None and reason.is_malformed else None
    return deny(classify(error), detail)


_CONNECT_HOST_FORBIDDEN = frozenset(r"/?#@\%")


class ScopeDecider:
    """Aplica o escopo da política a requisições e a túneis `CONNECT`."""

    def __init__(self, scope: Scope, path_mode: PathMode = "strict") -> None:
        """Compila o escopo no guarda do modo escolhido.

        Args:
            scope: Escopo já validado da política.
            path_mode: `strict` usa o `ScopeGuard`; `wide` usa o `WideScopeGuard` (só aqui,
                no proxy; ver `domain/wide_guard.py`).
        """
        self._guard = ScopeGuard(scope)
        self._wide = WideScopeGuard(scope) if path_mode == "wide" else None

    def decide_request(self, method: str, url: str) -> Verdict:
        """Decide uma requisição completa (método e URL absoluta).

        Args:
            method: Método exatamente como veio (minúsculas ou desconhecido são recusados).
            url: URL absoluta com o destino real da conexão.

        Returns:
            `ALLOW` se o guarda aceitou; senão recusa com o motivo classificado. No modo amplo,
            a liberação com leitura fora de `allow` traz `WIDE_READING_OUTSIDE_ALLOW`.
        """
        outbound = OutboundRequest(method=method, url=url)
        try:
            if self._wide is None:
                self._guard.ensure_allowed(outbound)
                return ALLOW
            outcome = self._wide.ensure_allowed(outbound)
        except ScopeViolation as error:
            return verdict_from(error)
        if outcome.leaves_allow:
            return Verdict(allowed=True, reason=Reason.ALLOWED, detail=WIDE_READING_OUTSIDE_ALLOW)
        return ALLOW

    def decide_connect(self, host: str, port: int) -> Verdict:
        """Decide a abertura de um túnel `CONNECT host:port` (sempre tratado como `https`).

        Só host e porta são conferidos aqui; caminho e método são conferidos em cada
        requisição interna do túnel, depois da interceptação do TLS.
        """
        # Barra, consulta, arroba etc. no "host" fariam a URL montada abaixo apontar para
        # outra origem (por exemplo "host/x" viraria o caminho /x): recusado antes.
        if not host or any(c in _CONNECT_HOST_FORBIDDEN or c.isspace() for c in host):
            return deny(Reason.MALFORMED_REQUEST)
        bracketed = f"[{host}]" if ":" in host and not host.startswith("[") else host
        try:
            self._guard.ensure_origin_allowed(f"https://{bracketed}:{port}/")
        except ScopeViolation as error:
            return verdict_from(error)
        return ALLOW
