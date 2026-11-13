"""Relógio falso: devolve sempre o instante informado."""

from datetime import UTC, datetime


class FixedClock:
    """Implementa `Clock` com um instante fixo, avançável pelo teste."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def advance_to(self, instant: datetime) -> None:
        self._instant = instant


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Atalho para um instante em UTC."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)
