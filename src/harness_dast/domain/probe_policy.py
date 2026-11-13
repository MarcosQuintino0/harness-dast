"""Política do `probe`: limites de tentativas, ritmo (balde de fichas) e espera por `Retry-After`.

Tudo recebe o tempo como argumento (segundos de um relógio injetado), nunca o lê. Este módulo
é puro.
"""

from typing import Final

REQUEST_TIMEOUT_SECONDS: Final = 15.0
"""Tempo máximo de uma requisição ao alvo (conexão, envio e leitura)."""

MAX_REAUTH_PER_REQUEST: Final = 1
"""Quantas vezes uma requisição pode provocar novo login após um 401."""

MAX_CSRF_REFRESH_PER_REQUEST: Final = 1
"""Quantas vezes uma requisição pode provocar nova busca do token CSRF após um 403."""

MAX_RATE_LIMIT_WAITS: Final = 3
"""Quantas esperas de `Retry-After` (429) uma requisição aceita antes de desistir."""

MAX_RETRY_AFTER_SECONDS: Final = 30.0
"""Teto de cada espera por `Retry-After`; valores maiores são reduzidos a este."""

DEFAULT_RETRY_AFTER_SECONDS: Final = 1.0
"""Espera quando o 429 não traz `Retry-After` utilizável."""

UNRESPONSIVE_THRESHOLD: Final = 5
"""Falhas de transporte consecutivas (timeout, conexão recusada, 502/503/504) que encerram o
probe com o alvo considerado indisponível."""

TRANSPORT_FAILURE_STATUSES: Final = frozenset({502, 503, 504})


def parse_retry_after(value: str | None) -> float:
    """Converte `Retry-After` (segundos inteiros) em espera limitada a `MAX_RETRY_AFTER_SECONDS`.

    Data HTTP, texto inválido, negativo ou ausente dão `DEFAULT_RETRY_AFTER_SECONDS`.
    """
    if value is not None and value.strip().isascii() and value.strip().isdigit():
        return min(float(int(value.strip())), MAX_RETRY_AFTER_SECONDS)
    return DEFAULT_RETRY_AFTER_SECONDS


class TokenBucket:
    """Balde de fichas para limitar requisições por segundo, com tempo injetado.

    Capacidade de uma ficha: nunca há rajada; cada requisição respeita o intervalo
    `1 / rate` desde a anterior.
    """

    def __init__(self, rate_per_second: float) -> None:
        """Cria o balde.

        Args:
            rate_per_second: Requisições por segundo, maior que 0.

        Raises:
            ValueError: Se a taxa não for positiva.
        """
        if rate_per_second <= 0:
            raise ValueError("a taxa deve ser maior que zero")
        self._interval = 1.0 / rate_per_second
        self._next_free: float | None = None

    def reserve(self, now: float) -> float:
        """Reserva a próxima vaga e diz quantos segundos esperar antes de usá-la.

        Args:
            now: Instante atual, em segundos (qualquer origem, desde que monotônica).

        Returns:
            Espera em segundos (0 quando já pode enviar). Chamar duas vezes seguidas reserva
            duas vagas.
        """
        start = now if self._next_free is None else max(now, self._next_free)
        self._next_free = start + self._interval
        return start - now
