"""Valores-modelo (placeholders) do `products/_template` que nunca valem como resposta real.

Usados pelo `profile validate` (pendência de execução) e pela carta estruturada (recusa na
entrada, ADR 0036). Este módulo é puro.
"""

from typing import Final
from urllib.parse import urlsplit

PLACEHOLDER_DOMAINS: Final = (
    "exemplo.com.br",
    "exemplo.com",
    "example.com",
    "example.org",
    "example.net",
)
PLACEHOLDER_REFERENCES: Final = frozenset({"SEC-0000", "CHANGE_ME"})
PLACEHOLDER_SECRET_PREFIXES: Final = ("MEU_PRODUTO_", "CHANGE_ME")
_SECRET_KINDS = ("env:", "keyring:")


def is_placeholder_host(host: str) -> bool:
    """Diz se `host` é um domínio de exemplo (ou subdomínio dele)."""
    name = host.lower()
    return any(name == domain or name.endswith("." + domain) for domain in PLACEHOLDER_DOMAINS)


def is_placeholder_reference(reference: str) -> bool:
    """Diz se a referência de autorização é a do modelo."""
    return reference.strip().upper() in PLACEHOLDER_REFERENCES


def is_placeholder_secret_name(name: str) -> bool:
    """Diz se o NOME de segredo (sem `env:`/`keyring:`) é o de exemplo."""
    return name.startswith(PLACEHOLDER_SECRET_PREFIXES)


def is_placeholder_text(text: str) -> bool:
    """Diz se um texto qualquer parece um valor-modelo.

    Cobre: `CHANGE_ME` em qualquer parte, a referência do modelo, domínio de exemplo (texto
    solto ou URL) e nome de segredo de exemplo (`env:MEU_PRODUTO_...`).
    """
    stripped = text.strip()
    if "CHANGE_ME" in stripped.upper() or is_placeholder_reference(stripped):
        return True
    for kind in _SECRET_KINDS:
        if stripped.startswith(kind):
            return is_placeholder_secret_name(stripped[len(kind) :])
    host = urlsplit(stripped).hostname if "://" in stripped else stripped
    return host is not None and is_placeholder_host(host)
