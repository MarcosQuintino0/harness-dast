"""Vigia local de fontes da trava, fora do caminho de concessao."""

from collections.abc import Callable
from threading import Event, Lock, Thread

from harness_dast.adapters.scope_proxy.decision import Reason
from harness_dast.adapters.scope_proxy.gate_watch_rule import SnapshotAction, judge_snapshot
from harness_dast.adapters.scope_proxy.watch_diagnostic import (
    Detection,
    DiagnosticResult,
    WatchCause,
    log_latch,
)

_INTERVAL = 0.05
_MAX_AGE = 0.2
_REVERIFY_TIMEOUT = 0.15


class GateWatch:
    """Publica leituras verificadas; falha, tempo-limite ou encerramento travam a saida."""

    def __init__(
        self,
        detect: Callable[[], Reason | Detection | None],
        clock: Callable[[], float],
        reverify_timeout: float = _REVERIFY_TIMEOUT,
    ) -> None:
        """Verifica as fontes antes de iniciar a vigia periodica.

        Args:
            detect: Leitura das fontes; devolve a negação ou `None` se íntegras.
            clock: Relógio monotônico.
            reverify_timeout: Espera máxima, em segundos reais, pela reverificação de um
                retrato velho; estourar trava.
        """
        self._detect = detect
        self._clock = clock
        self._lock = Lock()
        self._reverify_timeout = reverify_timeout
        self._inflight: Event | None = None
        self._stop = Event()
        self._started_at: float | None = None
        self._failure: Reason | None = None
        # Conserva o estado sanitizado de falha mesmo quando o emissor não inicia.
        self.result: DiagnosticResult | None = None
        self.run_once()
        self._thread = Thread(target=self._run, name="hdast-gate-watch", daemon=True)
        self._thread.start()

    def run_once(self) -> None:
        """Verifica fontes sem manter o lock consultado pela concessao."""
        started = self._clock()
        completed = False
        cause: WatchCause | None = None
        try:
            reason = self._detect()
            completed = True
        finally:
            with self._lock:
                if self._failure is None and not self._stop.is_set():
                    if not completed:
                        self._failure = Reason.APPROVAL_CHANGED
                        cause = WatchCause.DETECT_ERROR
                    elif reason is not None:
                        self._failure = reason.reason if isinstance(reason, Detection) else reason
                        cause = (
                            reason.cause
                            if isinstance(reason, Detection)
                            else WatchCause.DETECT_DENIED
                        )
                    elif self._started_at is None or started > self._started_at:
                        # Nunca recua o retrato: uma leitura lenta e antiga não sobrescreve a nova.
                        self._started_at = started
            if cause is not None:
                self.result = log_latch(cause)

    def check(self) -> Reason | None:
        """Concede só com retrato de idade <= 200 ms, reverificando na hora se estiver velho.

        Atraso da vigia não trava: a reverificação síncrona (uma por vez, com tempo-limite e
        sem segurar o lock) decide com o resultado novo. Mudança, erro, tempo-limite estourado,
        encerramento e relógio para trás travam como antes.
        """
        reverified = False
        while True:
            with self._lock:
                if self._failure is not None:
                    return self._failure
                judgement = judge_snapshot(
                    stopped=self._stop.is_set(),
                    started_at=self._started_at,
                    now=self._clock(),
                    max_age=_MAX_AGE,
                )
                if judgement.action is SnapshotAction.GRANT:
                    return None
                if judgement.action is SnapshotAction.REVERIFY and not reverified:
                    done, leader = self._join_reverification()
                else:
                    cause = judgement.cause or WatchCause.AGE
                    return self._latch_locked(cause)
            if not self._await_reverification(done, leader):
                return self._latch(WatchCause.REVERIFY_TIMEOUT)
            reverified = True

    def close(self) -> None:
        """Invalida imediatamente o snapshot sem esperar o fim de E/S."""
        with self._lock:
            first = self._failure is None
            self._failure = self._failure or Reason.APPROVAL_CHANGED
            self._stop.set()
        if first:
            self.result = log_latch(WatchCause.CLOSE)

    def _latch(self, cause: WatchCause) -> Reason:
        with self._lock:
            return self._latch_locked(cause)

    def _latch_locked(self, cause: WatchCause) -> Reason:
        """Trava (se ainda aberta) e agenda o diagnóstico; o lock já está tomado."""
        first = self._failure is None
        self._failure = self._failure or Reason.APPROVAL_CHANGED
        if first:
            # `log_latch` só agenda uma thread; não faz E/S sob o lock.
            self.result = log_latch(cause)
        return self._failure

    def _join_reverification(self) -> tuple[Event, bool]:
        """Entra na reverificação em andamento ou abre uma; o lock já está tomado."""
        if self._inflight is not None:
            return self._inflight, False
        self._inflight = Event()
        return self._inflight, True

    def _await_reverification(self, done: Event, leader: bool) -> bool:
        if leader:
            try:
                Thread(
                    target=self._reverify, args=(done,), name="hdast-gate-reverify", daemon=True
                ).start()
            except (RuntimeError, OSError, MemoryError):
                self._latch(WatchCause.DETECT_ERROR)
                self._finish_reverification(done)
                return True
        return done.wait(self._reverify_timeout)

    def _reverify(self, done: Event) -> None:
        try:
            self.run_once()
        except (OSError, ValueError, RuntimeError, MemoryError):
            pass  # run_once já travou com DETECT_ERROR; a mensagem externa não é propagada.
        finally:
            self._finish_reverification(done)

    def _finish_reverification(self, done: Event) -> None:
        with self._lock:
            if self._inflight is done:
                self._inflight = None
        done.set()

    def _run(self) -> None:
        while not self._stop.wait(_INTERVAL):
            self.run_once()
