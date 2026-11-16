"""Vigia local de fontes da trava, fora do caminho de concessao."""

from collections.abc import Callable
from threading import Event, Lock, Thread

from harness_dast.adapters.scope_proxy.decision import Reason

_INTERVAL = 0.05
_MAX_AGE = 0.2


class GateWatch:
    """Publica leituras verificadas; falha, atraso ou encerramento travam a saida."""

    def __init__(self, detect: Callable[[], Reason | None], clock: Callable[[], float]) -> None:
        """Verifica as fontes antes de iniciar a vigia periodica."""
        self._detect = detect
        self._clock = clock
        self._lock = Lock()
        self._stop = Event()
        self._started_at: float | None = None
        self._failure: Reason | None = None
        self.run_once()
        self._thread = Thread(target=self._run, name="hdast-gate-watch", daemon=True)
        self._thread.start()

    def run_once(self) -> None:
        """Verifica fontes sem manter o lock consultado pela concessao."""
        started = self._clock()
        completed = False
        try:
            reason = self._detect()
            completed = True
        finally:
            with self._lock:
                if self._failure is None and not self._stop.is_set():
                    if not completed:
                        self._failure = Reason.APPROVAL_CHANGED
                    elif reason is not None:
                        self._failure = reason
                    else:
                        self._started_at = started

    def check(self) -> Reason | None:
        """Recusa e trava estado ausente, envelhecido, encerrado ou com erro."""
        with self._lock:
            if self._failure is None:
                age = None if self._started_at is None else self._clock() - self._started_at
                if self._stop.is_set() or age is None or age < 0 or age > _MAX_AGE:
                    self._failure = Reason.APPROVAL_CHANGED
            return self._failure

    def close(self) -> None:
        """Invalida imediatamente o snapshot sem esperar o fim de E/S."""
        with self._lock:
            self._failure = self._failure or Reason.APPROVAL_CHANGED
            self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(_INTERVAL):
            self.run_once()
