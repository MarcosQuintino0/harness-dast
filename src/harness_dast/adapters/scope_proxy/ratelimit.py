"""Limitador de taxa que ATRASA em vez de recusar, com fila limitada.

O que garante: dois pedidos liberados nunca ficam a menos de `1 / taxa` segundos um do
outro (sem rajada), e a fila de espera tem tamanho máximo. O que não faz: não dorme (quem
chama espera o atraso devolvido) e não é seguro entre threads; o proxy roda num único laço
de eventos.
"""

from collections.abc import Callable


class RateLimiter:
    """Reserva horários de saída espaçados a `1 / requests_per_second`."""

    def __init__(
        self, *, requests_per_second: float, max_queued: int, monotonic: Callable[[], float]
    ) -> None:
        """Cria o limitador.

        Args:
            requests_per_second: Taxa máxima, maior que zero.
            max_queued: Quantos pedidos podem esperar ao mesmo tempo (pelo menos 1).
            monotonic: Relógio monotônico em segundos; entra por parâmetro para os testes.
        """
        if requests_per_second <= 0 or max_queued < 1:
            raise ValueError("taxa deve ser positiva e a fila ter ao menos 1 posição")
        self._interval = 1.0 / requests_per_second
        self._max_queued = max_queued
        self._monotonic = monotonic
        self._next_free = 0.0

    def reserve(self) -> float | None:
        """Reserva o próximo horário de saída.

        Returns:
            Segundos a esperar antes de enviar (0 se pode ir já), ou `None` se a fila está
            cheia; neste caso nada foi reservado.
        """
        now = self._monotonic()
        slot = max(now, self._next_free)
        delay = slot - now
        # Posições à frente na fila = atraso / intervalo. A tolerância absorve o erro de
        # ponto flutuante de somas repetidas do intervalo (0,1 + 0,1 ...).
        if delay > (self._max_queued - 1) * self._interval + 1e-9:
            return None
        self._next_free = slot + self._interval
        return delay

    def delay_until_grant(self) -> float:
        """Tempo restante até a próxima concessão efetiva."""
        return max(0.0, self._next_free - self._monotonic())

    def grant(self) -> None:
        """Marca a concessão no instante real, sem acumular crédito por atraso."""
        self._next_free = self._monotonic() + self._interval

    def defer(self, seconds: float) -> None:
        """Adia concessões sem aumentar a taxa nem diminuir um recuo existente."""
        self._next_free = max(self._next_free, self._monotonic() + seconds)
