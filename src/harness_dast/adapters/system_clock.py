"""Relógio do sistema, a implementação real da porta `Clock`."""

from datetime import UTC, datetime


class SystemClock:
    """Devolve a hora atual do sistema, em UTC."""

    def now(self) -> datetime:
        """Instante atual com fuso UTC."""
        return datetime.now(UTC)
