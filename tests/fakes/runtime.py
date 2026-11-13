"""Relógio, espera e aleatoriedade falsos: o tempo só anda quando o teste manda ou dorme."""

from datetime import UTC, datetime, timedelta


class ManualClock:
    """Implementa `Clock` e `Sleeper`: dormir avança o relógio sem esperar de verdade."""

    def __init__(self, instant: datetime | None = None) -> None:
        self._instant = instant or datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self._instant

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._instant += timedelta(seconds=seconds)

    def advance(self, seconds: float) -> None:
        self._instant += timedelta(seconds=seconds)


class FixedEntropy:
    """Implementa `EntropySource` com valores previsíveis."""

    def __init__(self, suffix: str = "7f3a", seed: int = 11) -> None:
        self._suffix = suffix
        self._seed = seed

    def hex_suffix(self) -> str:
        return self._suffix

    def seed(self) -> int:
        return self._seed
