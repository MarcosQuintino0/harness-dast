"""Categorias fechadas do diagnóstico sanitizado da vigia."""

import json
import logging
from enum import StrEnum
from threading import Thread
from typing import NamedTuple

from harness_dast.adapters.scope_proxy.decision import Reason


class WatchCause(StrEnum):
    """Causa observada na primeira trava, sem dados externos."""

    AGE = "age"
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


def log_latch(cause: WatchCause) -> None:
    """Agenda a emissão sem bloquear a trava em E/S de log."""
    Thread(target=_emit, args=(cause,), name="hdast-watch-diagnostic", daemon=True).start()


def _emit(cause: WatchCause) -> None:
    logging.getLogger("harness_dast.scope_proxy.watch").warning(
        "%s", json.dumps({"event": "gate_watch_latch", "category": cause.value})
    )
