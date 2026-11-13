"""Decisão por requisição: delega ao `ScopeGuard` e traduz o resultado em código estável.

O que garante: `allowed` só é verdadeiro se o `ScopeGuard` aceitou a requisição (a decisão de
escopo nunca é refeita aqui). Para o túnel `CONNECT` só confere host, esquema `https` e porta
contra as regras de permissão, pois o caminho e o método só existem dentro do túnel.
O que não faz: não resolve DNS, não olha cabeçalhos e não aplica prazo nem taxa.
"""

from dataclasses import dataclass
from enum import StrEnum

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard


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
    RATE_QUEUE_FULL = "rate_queue_full"
    AUDIT_FAILURE = "audit_failure"


@dataclass(frozen=True, slots=True)
class Verdict:
    """Resultado de uma checagem.

    Attributes:
        allowed: `True` só quando todas as checagens aplicáveis passaram.
        reason: Código do motivo (`ALLOWED` quando permitido).
    """

    allowed: bool
    reason: Reason


ALLOW = Verdict(allowed=True, reason=Reason.ALLOWED)


def deny(reason: Reason) -> Verdict:
    """Cria uma recusa com o motivo dado."""
    return Verdict(allowed=False, reason=reason)


# O ScopeGuard não expõe código de motivo, só a mensagem. Estes padrões são fixados pelos
# testes (que usam o ScopeGuard real). Qualquer outra mensagem vem da normalização da URL e
# vira MALFORMED_REQUEST; uma mensagem nova ou alterada só perde precisão do motivo, nunca
# abre acesso, porque a recusa vem da exceção e não da classificação.
_SCOPE_MESSAGES: tuple[tuple[str, str, Reason], ...] = (
    ("O caminho da requisição está em scope.deny_paths", "", Reason.DENY_PATH),
    ("Esquema ou porta de", "", Reason.ORIGIN_NOT_ALLOWED),
    ("O host ", "não está em scope.allow.", Reason.HOST_NOT_ALLOWED),
    ("O caminho da requisição não está coberto", "", Reason.PATH_NOT_ALLOWED),
    ("O método ", "não é permitido para este caminho em", Reason.METHOD_NOT_ALLOWED),
)


def classify(error: ScopeViolation) -> Reason:
    """Traduz a mensagem de uma `ScopeViolation` em código de motivo."""
    message = error.message
    for prefix, marker, reason in _SCOPE_MESSAGES:
        if message.startswith(prefix) and marker in message:
            return reason
    return Reason.MALFORMED_REQUEST


_CONNECT_HOST_FORBIDDEN = frozenset(r"/?#@\%")


class ScopeDecider:
    """Aplica o escopo da política a requisições e a túneis `CONNECT`."""

    def __init__(self, scope: Scope) -> None:
        """Compila o escopo no `ScopeGuard`.

        Args:
            scope: Escopo já validado da política.
        """
        self._guard = ScopeGuard(scope)

    def decide_request(self, method: str, url: str) -> Verdict:
        """Decide uma requisição completa (método e URL absoluta).

        Args:
            method: Método exatamente como veio (minúsculas ou desconhecido são recusados).
            url: URL absoluta com o destino real da conexão.

        Returns:
            `ALLOW` se o `ScopeGuard` aceitou; senão recusa com o motivo classificado.
        """
        try:
            self._guard.ensure_allowed(OutboundRequest(method=method, url=url))
        except ScopeViolation as error:
            return deny(classify(error))
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
            return deny(classify(error))
        return ALLOW
