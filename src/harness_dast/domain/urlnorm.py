"""Normalização de requisições de saída antes de qualquer decisão de escopo.

Princípio: toda decisão do `ScopeGuard` é tomada sobre a forma canônica produzida aqui, e
QUALQUER ambiguidade vira `ScopeViolation` (falha fechada). Em vez de tentar adivinhar como o
servidor ou o ZAP interpretariam uma URL estranha, a URL estranha é recusada.

Este módulo é puro: não resolve DNS, não lê relógio nem ambiente. Consequência: ele não
detecta um nome DNS permitido que aponte (ou passe a apontar) para um endereço interno
(DNS rebinding). Isso é coberto pela camada 3 do AD-11 (proxy de saída), não aqui.

Limitações conhecidas (reescritas de servidor que NÃO são fechadas aqui, pois exigiriam recusar
caminhos legítimos): IIS aceita `/admin::$DATA` e nomes curtos 8.3 (`/ADMIN~1`); servidores
que comparam caminho sem diferença de caixa (IIS) tratam `/Admin` como `/admin`: a negação já
ignora caixa, e a permissão (`allow`) é sensível a ela, o que só pode recusar a mais. Quem
precisa dessa garantia contra alvos Windows deve negar esses padrões em `deny_paths`.
"""

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote, unquote

from harness_dast.domain.host import ParsedHost, parse_host, safe_text, violation

KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
"""Métodos aceitos em regras e requisições. TRACE e CONNECT ficam de fora de propósito."""

MAX_URL_LENGTH = 2048
_PORT = re.compile(r"[0-9]{1,5}")
_URL = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)([^?#]*)")
_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def default_port(scheme: str) -> int:
    """Porta padrão do esquema: 443 para `https`, 80 para `http`."""
    return 443 if scheme == "https" else 80


@dataclass(frozen=True, slots=True)
class NormalizedRequest:
    """Requisição de saída em forma canônica; é sobre ela que o escopo decide.

    Attributes:
        method: Método HTTP em maiúsculas, um dos `KNOWN_METHODS`.
        scheme: `http` ou `https`.
        host: Host canônico.
        port: Porta efetiva (a padrão do esquema quando a URL não traz porta).
        segments: Segmentos do caminho já decodificados (uma vez), sem `.`/`..`/vazios.
    """

    method: str
    scheme: str
    host: ParsedHost
    port: int
    segments: tuple[str, ...]

    @property
    def path(self) -> str:
        """Caminho canônico decodificado, para mensagens e comparação."""
        return "/" + "/".join(self.segments)

    @property
    def origin(self) -> str:
        """`esquema://host[:porta]` canônico (porta omitida quando é a padrão)."""
        port = "" if self.port == default_port(self.scheme) else f":{self.port}"
        return f"{self.scheme}://{self.host.text}{port}"

    @property
    def url(self) -> str:
        """URL canônica sem consulta nem fragmento. Normalizá-la de novo dá o mesmo valor."""
        encoded = "".join("/" + quote(segment, safe="") for segment in self.segments)
        return self.origin + (encoded or "/")


def normalize_request(method: str, url: str) -> NormalizedRequest:
    """Normaliza método e URL absoluta de uma requisição de saída.

    Garantias: esquema só http/https; sem credenciais embutidas; host canônico (ver
    `parse_host`); porta numérica canônica; caminho decodificado uma única vez, sem `.`/`..`
    (nem codificados), sem parâmetros `;` (cru ou `%3B`), sem segmento terminado em ponto
    ou espaço nem iniciado por espaço (o servidor os apara antes de rotear), sem barras
    invertidas, sem `//`, sem barra codificada e sem dupla codificação. Consulta e fragmento
    são descartados (não entram na decisão de escopo), mas não podem conter controle nem espaço.

    Args:
        method: Método HTTP exatamente em maiúsculas (`GET`, `POST`...).
        url: URL absoluta.

    Returns:
        A requisição canônica.

    Raises:
        ScopeViolation: Para qualquer entrada ambígua, malformada ou fora dos limites acima.
    """
    if method not in KNOWN_METHODS:
        raise violation(
            f"Método HTTP {safe_text(str(method))} desconhecido ou fora do formato esperado.",
            hint="Use um destes, em maiúsculas: " + ", ".join(sorted(KNOWN_METHODS)) + ".",
        )
    _ensure_clean_url(url)
    match = _URL.match(url)
    if match is None:
        raise violation("A URL precisa ser absoluta, no formato http(s)://host/caminho.")
    scheme = match.group(1).lower()
    if scheme not in {"http", "https"}:
        raise violation(f"Esquema {safe_text(scheme)} não permitido; só http e https.")
    if not url[match.end(2) :].isascii():
        raise violation("Caminho, consulta e fragmento devem ser ASCII (use percent-encoding).")
    host_text, port = _split_authority(match.group(2), scheme)
    return NormalizedRequest(
        method=method,
        scheme=scheme,
        host=parse_host(host_text),
        port=port,
        segments=_normalize_path(match.group(3)),
    )


def _ensure_clean_url(url: str) -> None:
    if not url:
        raise violation("URL ausente.")
    if len(url) > MAX_URL_LENGTH:
        raise violation(f"URL maior que {MAX_URL_LENGTH} caracteres.")
    for char in url:
        # Espaço, controle, formatação (bidi, largura zero) e barra invertida têm
        # interpretações diferentes entre clientes, proxies e servidores.
        if char == "\\" or char.isspace() or unicodedata.category(char).startswith("C"):
            raise violation(
                "A URL contém espaço, caractere de controle ou barra invertida, que são recusados."
            )


def _split_authority(authority: str, scheme: str) -> tuple[str, int]:
    # Qualquer '@' é recusado: 'permitido.com@outro.com' conecta em outro.com, e
    # 'outro.com@permitido.com' engana revisores e filtros baseados em texto.
    if "@" in authority:
        raise violation("Credenciais embutidas na URL (usuário@host) são proibidas.")
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            raise violation("Host IPv6 sem colchete de fechamento.")
        host, rest = authority[: end + 1], authority[end + 1 :]
    else:
        host, separator, tail = authority.partition(":")
        rest = separator + tail
    return host, _parse_port(rest, scheme)


def _parse_port(rest: str, scheme: str) -> int:
    if rest == "":
        return default_port(scheme)
    digits = rest[1:]
    if not rest.startswith(":") or not _PORT.fullmatch(digits):
        raise violation("Porta malformada na URL.")
    port = int(digits)
    # '0080' é a mesma porta que '80' para o servidor, mas não para um filtro de texto.
    if not 1 <= port <= 65535 or str(port) != digits:
        raise violation("Porta fora do intervalo 1-65535 ou com zeros à esquerda.")
    return port


def _normalize_path(raw_path: str) -> tuple[str, ...]:
    if raw_path in {"", "/"}:
        return ()
    parts = raw_path[1:].split("/")
    if parts[-1] == "":
        parts.pop()  # barra final equivale a sem barra final
    return tuple(_decode_segment(part) for part in parts)


def _decode_segment(part: str) -> str:
    if part == "":
        raise violation("Caminho com segmento vazio ('//') é ambíguo e foi recusado.")
    if _PERCENT_ESCAPE.search(part):
        raise violation("Caminho com sequência '%' malformada.")
    try:
        decoded = unquote(part, errors="strict")
    except UnicodeDecodeError:
        raise violation("Caminho com percent-encoding que não é UTF-8 válido.") from None
    # Um '%' que sobra depois de decodificar uma vez é dupla codificação (%252e%252e).
    if "%" in decoded:
        raise violation("Caminho com dupla codificação ('%25...') foi recusado.")
    for char in decoded:
        if char in "/\\" or (char != " " and (char.isspace() or _is_control(char))):
            raise violation(
                "Caminho com barra codificada (%2f, %5c), controle ou espaço invisível."
            )
    _ensure_no_server_side_rewrite(decoded)
    return decoded


def _ensure_no_server_side_rewrite(segment: str) -> None:
    # Segurança: servidores de aplicação (Tomcat/Spring, IIS) reescrevem o caminho ANTES de
    # rotear: removem parâmetros ';x=1' (e tratam '..;' e '.;x' como '..' e '.'), aparam
    # espaço e ponto finais ('/admin ' e '/admin.' viram '/admin'). Se aceitássemos essas
    # formas, 'deny_paths: /admin' seria contornado. Em vez de adivinhar a reescrita de cada
    # servidor, recusamos a forma. A checagem roda sobre o segmento já decodificado, então
    # cobre ';' cru, '%3B', '%20' e '%2e' finais do mesmo jeito.
    if segment.split(";", 1)[0] in {".", ".."}:
        raise violation("Caminho com segmento '.' ou '..' (travessia) foi recusado.")
    if ";" in segment:
        raise violation("Caminho com parâmetro ';' é recusado: o servidor pode reescrevê-lo.")
    if segment.endswith((" ", ".")) or segment.startswith(" "):
        raise violation(
            "Caminho com segmento terminado em ponto ou espaço (ou iniciado por espaço) é "
            "recusado: o servidor pode aparar esses caracteres antes de rotear."
        )


def _is_control(char: str) -> bool:
    return unicodedata.category(char).startswith("C")


def resolve_location(*, base_url: str, location: str) -> str:
    """Resolve o cabeçalho `Location` de um redirecionamento para uma URL absoluta.

    Só três formas são aceitas: URL absoluta, `//host/caminho` (herda o esquema) e
    `/caminho` (herda a origem canônica). Caminho relativo sem barra inicial é recusado
    por ser ambíguo. O resultado deve ser conferido pelo `ScopeGuard` como qualquer
    requisição nova.

    Raises:
        ScopeViolation: Se `base_url` ou `location` forem recusados pela normalização.
    """
    base = normalize_request("GET", base_url)
    _ensure_clean_url(location)
    if location.startswith("//"):
        return f"{base.scheme}:{location}"
    if location.startswith("/"):
        return base.origin + location
    return location
