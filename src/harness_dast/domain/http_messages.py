"""Mensagens HTTP do harness e a invariante "nada sai sem passar pelo `ScopeGuard`".

Invariante de segurança (a que mais importa deste módulo): o único tipo que um cliente HTTP
aceita enviar é `ApprovedRequest`, e a única forma suportada de obter um é `approve`, que
chama `ScopeGuard.ensure_allowed` e só então o cria. O construtor exige uma marca privada
deste módulo; chamar `ApprovedRequest(...)` de fora levanta `TypeError`, e subclassear também.
Python não impede quem acessa `_MINT` de propósito, mas isso exige tocar num nome privado,
aparece em revisão e é coberto por teste. A aprovação vale para ESTA requisição imutável:
mudar método, URL, cabeçalhos ou corpo exige nova aprovação.

Este módulo é puro: não envia nada.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.routing_headers import is_routing_header
from harness_dast.domain.scope import OutboundRequest, ScopeGuard

Route = Literal["zap", "auth"]
"""Por onde a requisição sai: `zap` (pelo proxy do ZAP, que a aprende) ou `auth` (login e busca
do token CSRF: nunca pelo ZAP, para a senha não entrar no histórico dele)."""

MAX_RESPONSE_BYTES: Final = 256 * 1024
"""Teto de bytes lidos do corpo de uma resposta; o resto é descartado."""


class HttpRequest(BaseModel):
    """Requisição montada, ainda NÃO aprovada pelo escopo.

    Attributes:
        method: Método em maiúsculas.
        url: URL absoluta (com consulta já codificada).
        headers: Pares (nome, valor); os de autenticação são acrescentados por quem monta.
        body: Corpo já codificado, ou `None`.
        operation_id: Operação de origem (`auth.login` e `auth.csrf` para o próprio harness).
        account: Apelido da conta que envia, ou `None` (requisição anônima).
        route: Por onde sai.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=False)

    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    operation_id: str
    account: str | None = None
    route: Route = "zap"


_MINT: Final = object()


class ApprovedRequest:
    """Requisição que o `ScopeGuard` aprovou; o único tipo que um cliente HTTP envia.

    Só `approve` cria instâncias (ver o docstring do módulo). É imutável e expõe a
    requisição aprovada por `request`.
    """

    __slots__ = ("_request",)

    def __init__(self, request: HttpRequest, *, _mint: object) -> None:
        """Não chame diretamente: use `approve`.

        Raises:
            TypeError: Sempre que chamado sem a marca privada deste módulo.
        """
        if _mint is not _MINT:
            raise TypeError("ApprovedRequest só pode ser criado por approve(guard, request).")
        object.__setattr__(self, "_request", request)

    def __init_subclass__(cls, **_kwargs: object) -> None:
        """Proíbe subclasses: uma subclasse poderia contornar a marca."""
        raise TypeError("ApprovedRequest não pode ser estendido.")

    def __setattr__(self, name: str, value: object) -> None:
        """Mantém a instância imutável."""
        raise AttributeError("ApprovedRequest é imutável.")

    @property
    def request(self) -> HttpRequest:
        """A requisição aprovada."""
        request: HttpRequest = object.__getattribute__(self, "_request")
        return request


def approve(guard: ScopeGuard, request: HttpRequest) -> ApprovedRequest:
    """Confere a requisição no escopo e devolve a versão aprovada.

    Raises:
        ScopeViolation: Se a requisição estiver fora do escopo ou em `deny_paths`, ou se trouxer
            cabeçalho de roteamento (`Host`, `Transfer-Encoding`...), que só o cliente HTTP
            define (nada é devolvido, então nada pode ser enviado).
    """
    for name, _value in request.headers:
        if is_routing_header(name):
            raise ScopeViolation(
                f"o cabeçalho {name} controla o roteamento e não pode ser enviado.",
                hint="Esse cabeçalho é definido só pelo cliente HTTP da ferramenta.",
            )
    guard.ensure_allowed(OutboundRequest(method=request.method, url=request.url))
    return ApprovedRequest(request, _mint=_MINT)


class HttpResponse(BaseModel):
    """Resposta do alvo, reduzida ao que o harness usa.

    Attributes:
        status: Código HTTP.
        content_type: Valor de `Content-Type`, ou `None`.
        retry_after: Valor de `Retry-After`, ou `None`.
        location: Valor de `Location` (só faz sentido em 3xx), ou `None`.
        body: Corpo, no máximo `MAX_RESPONSE_BYTES`.
        body_truncated: Se o corpo passou do teto e foi cortado.
        elapsed_ms: Duração da requisição em milissegundos.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: int
    content_type: str | None = None
    retry_after: str | None = None
    location: str | None = None
    body: bytes = b""
    body_truncated: bool = False
    elapsed_ms: int = 0
