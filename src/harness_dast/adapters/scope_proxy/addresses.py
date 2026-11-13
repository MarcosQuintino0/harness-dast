"""Proteção do endereço resolvido: o que o nome DNS permitido NÃO pode alcançar.

O `ScopeGuard` é puro e decide por nome; um nome permitido pode apontar (ou passar a apontar,
DNS rebinding) para loopback, rede privada ou metadados da nuvem. Este módulo confere os
endereços que o DNS devolveu. O que garante: sem `allow_local`, só endereço global passa;
com `allow_local`, passam também loopback, rede privada e CGNAT; link-local (inclui
169.254.169.254), não especificado, multicast e reservado nunca passam. IPv6 que embute IPv4
(mapeado, 6to4, Teredo e NAT64 `64:ff9b::/96`) é avaliado como o IPv4; o NAT64 de uso local
(`64:ff9b:1::/48`) nunca passa. O Python 3.13 (a imagem do proxy) classifica o NAT64 como
global, por isso a regra é explícita e não depende da versão. O que não faz: não resolve DNS.
"""

import ipaddress
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv6Address

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, Verdict, deny

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL_USE = ipaddress.ip_network("64:ff9b:1::/48")


def _unwrap(address: IPv4Address | IPv6Address) -> IPv4Address | IPv6Address:
    if isinstance(address, IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
        if address.sixtofour is not None:
            return address.sixtofour
        if address.teredo is not None:
            return address.teredo[1]
        if address in _NAT64:
            return IPv4Address(address.packed[-4:])
    return address


def _never_allowed(address: IPv4Address | IPv6Address) -> bool:
    if address in {IPv4Address("169.254.169.254"), IPv6Address("fd00:ec2::254")}:
        return True
    if isinstance(address, IPv6Address) and address in _NAT64_LOCAL_USE:
        return True
    return (
        address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or (address.is_reserved and not address.is_loopback)
    )


def _is_local(address: IPv4Address | IPv6Address) -> bool:
    if address.is_loopback or address.is_private:
        return True
    return isinstance(address, IPv4Address) and address in _CGNAT


def check_addresses(addresses: Iterable[str], *, allow_local: bool) -> Verdict:
    """Confere todos os endereços devolvidos pelo DNS; basta um proibido para recusar.

    Args:
        addresses: Endereços IP em texto. Lista vazia ou texto que não é IP é recusado.
        allow_local: `True` quando a regra que casou o host declara `allow_local: true`.

    Returns:
        `ALLOW` ou recusa com `ADDRESS_FORBIDDEN`.
    """
    seen = False
    for text in addresses:
        seen = True
        try:
            address = _unwrap(ipaddress.ip_address(text))
        except ValueError:
            return deny(Reason.ADDRESS_FORBIDDEN)
        if _never_allowed(address):
            return deny(Reason.ADDRESS_FORBIDDEN)
        if address.is_global:
            continue
        if not (allow_local and _is_local(address)):
            return deny(Reason.ADDRESS_FORBIDDEN)
    return ALLOW if seen else deny(Reason.DNS_FAILURE)
