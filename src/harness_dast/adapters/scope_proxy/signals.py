"""Leitura de sinais de erro interno numa resposta liberada (ADR 0049). Sem mitmproxy.

O que garante: devolve só NOMES de categoria (nunca trecho); lê no máximo `SCAN_LIMIT_BYTES` do
corpo (e `COMPRESSED_INPUT_LIMIT` de entrada comprimida, com saída limitada, então uma bomba de
descompressão não gasta memória); codificação desconhecida ou corpo malformado viram `skipped`,
nunca exceção. O que não faz: não decide nada sobre a resposta (só observa), não guarda o texto
e não conhece política de escopo. `read_response_signals` é o único ponto de entrada da cerca e
falha aberta de propósito: um defeito de leitura jamais pode virar recusa nem travar o proxy.
"""

import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from harness_dast.domain.error_signal_catalog import (
    COMPRESSED_INPUT_LIMIT,
    SCAN_LIMIT_BYTES,
    SignalCategory,
    SignalSkip,
    detect_signals,
    is_scannable,
)

_GZIP = frozenset({"gzip", "x-gzip"})
_PLAIN = frozenset({"", "identity"})


@dataclass(frozen=True)
class SignalReading:
    """O que a leitura de uma resposta encontrou.

    Attributes:
        categories: Categorias de sinal, na ordem do catálogo.
        skipped: Por que a resposta não foi lida (`type`, `encoding`, `empty`, `error`), ou
            `None` quando foi lida.
    """

    categories: tuple[SignalCategory, ...] = ()
    skipped: SignalSkip | None = None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _decompress(body: bytes, encoding: str) -> bytes | None:
    """Primeiros bytes descomprimidos, ou `None` se o dado não é gzip/deflate válido."""
    data = body[:COMPRESSED_INPUT_LIMIT]
    # 16 + MAX_WBITS: gzip; MAX_WBITS: zlib; -MAX_WBITS: deflate cru (alguns servidores o mandam).
    windows = (16 + zlib.MAX_WBITS,) if encoding in _GZIP else (zlib.MAX_WBITS, -zlib.MAX_WBITS)
    for window in windows:
        try:
            return zlib.decompressobj(window).decompress(data, SCAN_LIMIT_BYTES)
        except zlib.error:
            continue
    return None


def inspect_response(
    method: str, status: int, headers: Mapping[str, str], raw_body: bytes | None
) -> SignalReading:
    """Traduz uma resposta (corpo ainda codificado, como veio do alvo) numa leitura.

    Nunca levanta por causa do corpo: erro de `zlib` e codificação desconhecida viram
    `skipped = "encoding"`.
    """
    if not is_scannable(status, method, _header(headers, "content-type")):
        return SignalReading(skipped="type")
    if not raw_body:
        return SignalReading(skipped="empty")
    encoding = (_header(headers, "content-encoding") or "").strip().lower()
    if encoding in _PLAIN:
        data = raw_body[:SCAN_LIMIT_BYTES]
    elif encoding in _GZIP or encoding == "deflate":
        decoded = _decompress(raw_body, encoding)
        if decoded is None:
            return SignalReading(skipped="encoding")
        data = decoded
    else:
        return SignalReading(skipped="encoding")
    if not data:
        return SignalReading(skipped="empty")
    return SignalReading(categories=detect_signals(data.decode("utf-8", errors="replace")))


def read_response_signals(
    method: str,
    status: int,
    headers: Mapping[str, str],
    raw_body: bytes | None,
    *,
    inspect: Callable[
        [str, int, Mapping[str, str], bytes | None], SignalReading
    ] = inspect_response,
) -> SignalReading:
    """Lê a resposta sem nunca levantar: falha inesperada vira `skipped = "error"`.

    Falha aberta de propósito (ADR 0049, seção 2): a leitura só observa; recusar uma resposta
    por defeito dela criaria uma nova forma de negar serviço ao próprio teste. `inspect` existe
    para o teste injetar uma falha difícil de provocar.
    """
    try:
        return inspect(method, status, headers, raw_body)
    except Exception:  # noqa: BLE001 - falha aberta documentada acima; nada aqui decide escopo
        return SignalReading(skipped="error")
