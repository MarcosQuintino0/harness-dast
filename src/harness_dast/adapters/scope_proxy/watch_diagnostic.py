"""Categorias fechadas do diagnóstico sanitizado da vigia."""

import json
import sys
from enum import StrEnum
from threading import Lock, Thread
from typing import NamedTuple, TextIO

from harness_dast.adapters.scope_proxy.decision import Reason

_LATCH_EVENT = "gate_watch_latch"
_SLOW_DENY_EVENT = "gate_watch_slow_deny"


class WatchCause(StrEnum):
    """Causa observada na primeira trava, sem dados externos."""

    SLOW_DENY = "slow_deny"
    CLOCK = "clock"
    NO_SNAPSHOT = "no_snapshot"
    CLOSE = "close"
    DETECT_ERROR = "detect_error"
    DETECT_DENIED = "detect_denied"
    STOP = "stop_or_inaccessible"
    ACCESS = "access"
    UNSTABLE = "unstable"
    IDENTITY = "identity"
    METADATA = "metadata"
    HASH = "hash"
    SIZE_OR_TYPE = "size_or_type"
    APPROVAL_INVALID = "approval_invalid"


class Detection(NamedTuple):
    """Recusa e categoria segura observadas na mesma verificação."""

    reason: Reason
    cause: WatchCause


class DiagnosticStatus(StrEnum):
    """Resultado sanitizado da tentativa de emissão."""

    PENDING = "pending"
    SENT = "sent"
    START_FAILED = "start_failed"
    WRITE_FAILED = "write_failed"


class DiagnosticResult:
    """Guarda resultado consultável sem transportar exceção ou dado externo."""

    def __init__(self) -> None:
        """Inicia a tentativa em estado pendente."""
        self._lock = Lock()
        self._status = DiagnosticStatus.PENDING

    @property
    def status(self) -> DiagnosticStatus:
        """Devolve o estado da tentativa sem esperar a escrita."""
        with self._lock:
            return self._status

    def finish(self, status: DiagnosticStatus) -> None:
        """Publica o resultado final da tentativa."""
        with self._lock:
            self._status = status


class StructuredWatchLogger:
    """Registra exclusivamente um evento sanitizado em JSON no fluxo recebido."""

    def __init__(self, stream: TextIO) -> None:
        """Recebe o destino sem alterar a configuração global de logs."""
        self._stream = stream

    def warning(self, cause: WatchCause, event: str = _LATCH_EVENT) -> bool:
        """Retorna se o fluxo aceitou o registro completo e confirmou a descarga."""
        payload = json.dumps({"event": event, "category": cause.value}) + "\n"
        if self._stream.write(payload) != len(payload):
            return False
        self._stream.flush()
        return True


def log_latch(cause: WatchCause) -> DiagnosticResult:
    """Agenda saída sanitizada da trava e registra falhas previsíveis sem afetar a trava."""
    return _schedule(cause, _LATCH_EVENT)


def log_slow_deny() -> DiagnosticResult:
    """Agenda saída sanitizada de uma negação por lentidão (sem trava)."""
    return _schedule(WatchCause.SLOW_DENY, _SLOW_DENY_EVENT)


def _schedule(cause: WatchCause, event: str) -> DiagnosticResult:
    result = DiagnosticResult()
    try:
        Thread(
            target=_emit, args=(cause, result, event), name="hdast-watch-diagnostic", daemon=True
        ).start()
    except (RuntimeError, OSError, MemoryError):
        result.finish(DiagnosticStatus.START_FAILED)
    return result


def _emit(cause: WatchCause, result: DiagnosticResult, event: str = _LATCH_EVENT) -> None:
    try:
        sent = StructuredWatchLogger(sys.stderr).warning(cause, event)
    except (OSError, ValueError, RuntimeError, MemoryError):
        result.finish(DiagnosticStatus.WRITE_FAILED)
    else:
        result.finish(DiagnosticStatus.SENT if sent else DiagnosticStatus.WRITE_FAILED)
