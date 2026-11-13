"""Cabeçalhos de roteamento e de enquadramento da conexão, que o harness nunca deixa vir de fora.

Quem controla esses cabeçalhos é o cliente HTTP. Se um documento OpenAPI (entrada não confiável)
ou um chamador pudesse defini-los, um `Host` desviaria a requisição para outro virtual host mesmo
com a URL dentro do escopo, e `Transfer-Encoding` ou `Content-Length` abririam a porta para
contrabando de requisição. Este módulo é puro.
"""

_ROUTING_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "upgrade",
        "te",
        "expect",
        "trailer",
        "keep-alive",
        "forwarded",
        "via",
    }
)
_ROUTING_HEADER_PREFIXES = ("proxy-", "x-forwarded-")


def is_routing_header(name: str) -> bool:
    """Diz se o cabeçalho é de roteamento ou de enquadramento da conexão.

    Garante: a decisão é por nome, sem diferenciar maiúsculas. Não faz: não olha o valor.

    Args:
        name: Nome do cabeçalho.

    Returns:
        `True` para `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Upgrade`, `TE`,
        `Expect`, `Trailer`, `Keep-Alive`, `Forwarded`, `Via`, `Proxy-*` e `X-Forwarded-*`.
    """
    lowered = name.strip().lower()
    return lowered in _ROUTING_HEADERS or lowered.startswith(_ROUTING_HEADER_PREFIXES)
