"""Cliente HTTP do alvo sobre `httpx` (implementa `TargetClient`).

Garantias, todas testadas contra um servidor local real:

- só envia `ApprovedRequest` (requisição aprovada pelo `ScopeGuard`); o adaptador não decide
  escopo;
- NÃO segue redirecionamentos (um 3xx volta como resposta);
- ignora variáveis de ambiente de proxy (`trust_env=False`): a rota é escolhida pela
  configuração, nunca por `HTTP_PROXY`;
- rota `zap` sai pelo proxy do ZAP (que aprende a requisição); rota `auth` (login e token
  CSRF) sai direta ou por `auth_proxy_url`, para a senha não entrar no histórico do ZAP;
- tempo limite em conexão, envio e leitura; corpo da resposta lido até um teto de bytes;
- TLS verificado por padrão; `verify_tls=False` só chega aqui se o perfil o permitiu (host
  local); a rota `zap` pode usar a CA do ZAP (`zap_ca_file`);
- cookies guardados por conta (nunca compartilhados entre contas), aplicados em cada
  requisição da conta.

Falhas de `httpx` viram erros do harness: tempo esgotado -> `TargetTimeout`; falha de
conexão ao proxy do ZAP -> `ExternalToolError`; demais falhas de transporte ->
`TargetUnreachable`. Nenhuma mensagem inclui URL, cabeçalho ou corpo.
"""

import ssl
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

import httpx

from harness_dast.domain.errors import ExternalToolError, TargetTimeout, TargetUnreachable
from harness_dast.domain.http_messages import MAX_RESPONSE_BYTES, ApprovedRequest, HttpResponse

USER_AGENT = "harness-dast"


@dataclass(frozen=True)
class TargetClientSettings:
    """Configuração do cliente.

    Attributes:
        zap_proxy_url: URL do proxy do ZAP (rota `zap`).
        auth_proxy_url: Proxy da rota `auth`, ou `None` para sair direto.
        timeout_seconds: Tempo limite de conexão, envio e leitura.
        verify_tls: Se o certificado do alvo é verificado.
        zap_ca_file: Certificado da CA do ZAP para HTTPS pela rota `zap`, ou `None`.
        max_body_bytes: Teto de bytes lidos do corpo da resposta.
    """

    zap_proxy_url: str
    auth_proxy_url: str | None = None
    timeout_seconds: float = 15.0
    verify_tls: bool = True
    zap_ca_file: Path | None = None
    max_body_bytes: int = MAX_RESPONSE_BYTES


class HttpxTargetClient:
    """Envia requisições aprovadas (veja o docstring do módulo)."""

    def __init__(self, settings: TargetClientSettings) -> None:
        """Cria o cliente; as conexões só abrem no primeiro envio.

        Args:
            settings: Configuração.
        """
        self._settings = settings
        self._zap = self._build_client(settings.zap_proxy_url, self._zap_verify(settings))
        self._auth = self._build_client(settings.auth_proxy_url, settings.verify_tls)
        # conta -> origem (`host:porta`) -> cookies: o cookie de sessão nunca vai a outro host.
        self._cookies: dict[str, dict[str, dict[str, str]]] = {}

    @staticmethod
    def _zap_verify(settings: TargetClientSettings) -> bool | ssl.SSLContext:
        if settings.zap_ca_file is not None:
            return ssl.create_default_context(cafile=str(settings.zap_ca_file))
        return settings.verify_tls

    def _build_client(self, proxy: str | None, verify: bool | ssl.SSLContext) -> httpx.Client:
        timeout = httpx.Timeout(self._settings.timeout_seconds)
        return httpx.Client(
            proxy=proxy,
            verify=verify,
            timeout=timeout,
            # Sem conexão reaproveitada. Medido contra o Spring Boot real atrás do ZAP e do proxy
            # de escopo: a terceira requisição numa conexão persistente ficava pendurada até o
            # tempo limite (o servidor encerra a conexão e o intermediário não percebe). O volume
            # do harness é baixo (cinco requisições por segundo), então abrir uma conexão por
            # requisição custa pouco.
            limits=httpx.Limits(max_keepalive_connections=0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        """Fecha as conexões."""
        self._zap.close()
        self._auth.close()

    def cookie_value(self, account: str, name: str) -> str | None:
        """Valor do cookie `name` guardado para a conta (da origem mais recente), ou `None`."""
        for jar in reversed(list(self._cookies.get(account, {}).values())):
            if name in jar:
                return jar[name]
        return None

    def send(self, approved: ApprovedRequest) -> HttpResponse:
        """Envia a requisição aprovada (veja o docstring do módulo para as garantias).

        Raises:
            TargetTimeout: O alvo não respondeu a tempo.
            TargetUnreachable: Falha de conexão ou de protocolo com o alvo.
            ExternalToolError: O proxy do ZAP recusou ou não aceitou a conexão.
        """
        request = approved.request
        via_zap = request.route == "zap"
        client = self._zap if via_zap else self._auth
        # O httpx guarda cookies no cliente; eles nunca podem vazar entre contas.
        self._zap.cookies.clear()
        self._auth.cookies.clear()
        started = perf_counter()
        try:
            with client.stream(
                request.method,
                request.url,
                headers=self._headers(request.account, _origin(request.url), request.headers),
                content=request.body,
            ) as response:
                body, truncated = self._read_capped(response)
                self._store_cookies(request.account, _origin(request.url), response)
                elapsed = int((perf_counter() - started) * 1000)
                return self._to_response(response, body, truncated, elapsed)
        except httpx.TimeoutException:
            raise TargetTimeout(
                "O alvo não respondeu dentro do tempo limite.",
                hint="Confira a saúde do alvo; ele pode estar saturado ou fora do ar.",
            ) from None
        except httpx.ProxyError:
            raise _proxy_error() from None
        except httpx.ConnectError:
            if via_zap:
                # Na rota `zap` a conexão que falha é a do proxy, não a do alvo.
                raise _proxy_error() from None
            raise _unreachable() from None
        except (httpx.TransportError, httpx.InvalidURL):
            raise _unreachable() from None

    def _headers(
        self, account: str | None, origin: str, headers: tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        merged = [(name, value) for name, value in headers if name.lower() != "cookie"]
        explicit = [value for name, value in headers if name.lower() == "cookie"]
        jar = self._cookies.get(account, {}).get(origin, {}) if account is not None else {}
        pairs = [f"{name}={value}" for name, value in jar.items()]
        cookie = "; ".join([*pairs, *explicit])
        if cookie:
            merged.append(("Cookie", cookie))
        return merged

    def _read_capped(self, response: httpx.Response) -> tuple[bytes, bool]:
        limit = self._settings.max_body_bytes
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                chunks.append(chunk[: limit - (size - len(chunk))])
                return b"".join(chunks), True
            chunks.append(chunk)
        return b"".join(chunks), False

    def _store_cookies(self, account: str | None, origin: str, response: httpx.Response) -> None:
        if account is None:
            return
        jar = self._cookies.setdefault(account, {}).setdefault(origin, {})
        for raw in response.headers.get_list("set-cookie"):
            parsed: SimpleCookie = SimpleCookie()
            try:
                parsed.load(raw)
            except CookieError:
                continue
            for name, morsel in parsed.items():
                if not morsel.value or morsel["max-age"] == "0":
                    jar.pop(name, None)
                else:
                    jar[name] = morsel.value

    @staticmethod
    def _to_response(
        response: httpx.Response, body: bytes, truncated: bool, elapsed_ms: int
    ) -> HttpResponse:
        return HttpResponse(
            status=response.status_code,
            content_type=response.headers.get("content-type"),
            retry_after=response.headers.get("retry-after"),
            location=response.headers.get("location"),
            body=body,
            body_truncated=truncated,
            elapsed_ms=elapsed_ms,
        )


def _origin(url: str) -> str:
    """`host:porta` da URL em minúsculas: a chave do jar de cookies."""
    return urlsplit(url).netloc.rpartition("@")[2].lower()


def _proxy_error() -> ExternalToolError:
    return ExternalToolError(
        "O proxy do ZAP não aceitou a conexão.",
        hint="Confira se o ZAP está no ar e se HDAST_ZAP_PROXY_URL está certo.",
    )


def _unreachable() -> TargetUnreachable:
    return TargetUnreachable(
        "Não foi possível falar com o alvo (conexão recusada, reiniciada ou interrompida).",
        hint="Confira se o alvo está no ar e acessível pela rede do ambiente de teste.",
    )
