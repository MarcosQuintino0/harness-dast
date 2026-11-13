"""Host de uma requisição em forma canônica (nome DNS em punycode ou IP sem ambiguidade).

Tudo que é ambíguo (IP em formato decimal/hex/octal, IPv6 que embute IPv4, IDNA que muda ao
ser mapeado, metadados da nuvem) vira `ScopeViolation`. Este módulo é puro: não resolve DNS.
As mensagens de recusa de host não repetem o valor recebido: ele pode ser um segredo digitado
no lugar errado e a mensagem acaba em envelope e log.
"""

import ipaddress
import re
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address

from harness_dast.domain.errors import ScopeViolation

_HINT = "Revise a URL; o escopo é imposto sobre a forma canônica e URLs ambíguas são recusadas."

_MAX_HOST_LENGTH = 253
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_NUMERIC_LABEL = re.compile(r"(?:0[xX][0-9a-fA-F]*|[0-9]+)")
_METADATA_IPS = frozenset({IPv4Address("169.254.169.254"), IPv6Address("fd00:ec2::254")})
_METADATA_NAMES = frozenset({"metadata.google.internal", "metadata", "instance-data"})
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")


def violation(message: str, hint: str = _HINT) -> ScopeViolation:
    """Cria a `ScopeViolation` padrão da normalização, com dica de como corrigir."""
    return ScopeViolation(message, hint=hint)


def safe_text(text: str) -> str:
    """Texto seguro para mensagens: sem controle, truncado. Nunca usado com a URL inteira."""
    return ascii(text)[:80]


@dataclass(frozen=True, slots=True)
class ParsedHost:
    """Host em forma canônica.

    Attributes:
        name: Nome em minúsculas e ASCII (punycode), ou o IP em forma canônica sem colchetes.
        ip: Endereço quando o host é um IP literal; `None` quando é nome DNS.
    """

    name: str
    ip: IPv4Address | IPv6Address | None

    @property
    def text(self) -> str:
        """Forma de texto canônica; IPv6 vem entre colchetes, como numa URL."""
        return f"[{self.name}]" if isinstance(self.ip, IPv6Address) else self.name

    @property
    def is_local(self) -> bool:
        """Verdadeiro para IP literal, `localhost`, nomes de rótulo único e `.local`/`.internal`.

        São os hosts que só fazem sentido no laboratório local (contêineres Docker) e por
        isso exigem `allow_local: true` na regra.
        """
        if self.ip is not None:
            return True
        return (
            self.name == "localhost" or "." not in self.name or self.name.endswith(_LOCAL_SUFFIXES)
        )

    @property
    def is_lab_address(self) -> bool:
        """Verdadeiro se o IP literal é loopback ou privado (e nunca link-local)."""
        ip = self.ip
        if ip is None:
            return False
        return ip.is_loopback or (ip.is_private and not ip.is_link_local)


def parse_host(raw: str) -> ParsedHost:
    """Converte o host escrito numa URL ou regra para a forma canônica.

    Args:
        raw: Host como escrito, sem porta; IPv6 entre colchetes.

    Returns:
        O host canônico (minúsculas, sem ponto final, punycode, IP sem ambiguidade).

    Raises:
        ScopeViolation: Se o host for vazio, tiver caractere inválido, falhar na codificação
            IDNA, for IP em forma não canônica (decimal, hexadecimal, octal, abreviada), for
            IPv4 embutido em IPv6, ou for endereço de metadados da nuvem ou faixa bloqueada.
    """
    if not raw:
        raise violation("Host ausente na URL.")
    if raw.startswith("["):
        parsed = _parse_ipv6(raw)
    else:
        name = _to_ascii_name(raw)
        _ensure_ldh(name)
        parsed = _parse_ipv4_or_name(name)
    _ensure_not_forbidden(parsed)
    return parsed


def _parse_ipv6(raw: str) -> ParsedHost:
    inner = raw[1:-1]
    # Escopo de zona (%eth0) muda o destino conforme a máquina: sempre recusado.
    if not raw.endswith("]") or "%" in inner:
        raise violation("Host IPv6 malformado ou com identificador de zona.")
    try:
        address = ipaddress.IPv6Address(inner)
    except ipaddress.AddressValueError:
        raise violation("Host IPv6 inválido.") from None
    # Formas que embutem um IPv4 permitiriam contornar regras escritas para IPv4.
    if address.ipv4_mapped or address.sixtofour or address.teredo:
        raise violation("IPv6 que embute IPv4 (mapeado, 6to4, Teredo) é ambíguo e foi recusado.")
    return ParsedHost(str(address), address)


def _to_ascii_name(raw: str) -> str:
    # Uma única forma canônica: tudo vira ASCII/punycode. Letras parecidas de outro
    # alfabeto (ex.: o 'a' cirílico) geram um punycode diferente e portanto não casam com
    # o host permitido. Se a codificação falhar, o host é recusado em vez de "limpo".
    lowered = raw.lower()
    try:
        encoded = lowered.encode("idna")
        decoded = encoded.decode("idna")  # também confere o ida e volta de rótulos xn--
    except UnicodeError:
        raise violation("O host falhou na codificação IDNA.") from None
    # O codec IDNA aplica mapeamentos (ß vira ss, largura total vira ASCII, '。' vira '.').
    # Navegadores e bibliotecas divergem nesses mapeamentos; então só entra host que o
    # mapeamento deixa idêntico, e a forma "mapeada" nunca é adivinhada.
    if not lowered.isascii() and decoded != lowered:
        raise violation("O host não está em forma IDNA canônica.")
    name = encoded.decode("ascii")
    # Um ponto final é a mesma coisa que sem ponto. Pontos repetidos (rótulo vazio) já
    # foram recusados na codificação IDNA acima e de novo em `_ensure_ldh`.
    return name.removesuffix(".")


def _ensure_ldh(name: str) -> None:
    labels = name.split(".")
    if len(name) > _MAX_HOST_LENGTH or not all(_LABEL.fullmatch(label) for label in labels):
        # Cobre curingas, '@', ':', '%', '_', espaços e qualquer resíduo de normalização
        # Unicode (ex.: arroba de largura total que vira '@').
        raise violation("O host contém caracteres não permitidos em nome DNS.")


def _parse_ipv4_or_name(name: str) -> ParsedHost:
    last_label = name.rsplit(".", 1)[-1]
    if not _NUMERIC_LABEL.fullmatch(last_label):
        return ParsedHost(name, None)
    # Último rótulo numérico: navegadores e bibliotecas tratam como IPv4 (decimal único,
    # hexadecimal, octal, abreviado). Só a forma decimal pontuada canônica é aceita.
    try:
        address = ipaddress.IPv4Address(name)
    except ipaddress.AddressValueError:
        raise violation(
            "O host parece um IP em forma não canônica (decimal, hex, octal ou abreviada) "
            "e foi recusado."
        ) from None
    return ParsedHost(str(address), address)


def _ensure_not_forbidden(host: ParsedHost) -> None:
    ip = host.ip
    if ip is not None:
        if ip in _METADATA_IPS:
            raise violation("Endereço de metadados da nuvem é sempre proibido.")
        if ip.is_link_local or ip.is_unspecified or ip.is_multicast or _is_reserved(ip):
            raise violation(
                "IP em faixa proibida (link-local, não especificado, multicast ou reservado)."
            )
    elif host.name in _METADATA_NAMES:
        raise violation("Nome de serviço de metadados da nuvem é sempre proibido.")


def _is_reserved(ip: IPv4Address | IPv6Address) -> bool:
    # ::1 cai na faixa reservada ::/8 do IPv6, mas é loopback e precisa chegar à política
    # de allow_local; só as demais reservadas são bloqueadas aqui.
    return ip.is_reserved and not ip.is_loopback
