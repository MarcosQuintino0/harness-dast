"""Vínculo local imutável a arquivos autorizados durante a vida do proxy."""

import hashlib
import os
import stat
import sys
from pathlib import Path

from pydantic import ValidationError

from harness_dast.adapters.scope_proxy.watch_diagnostic import WatchCause
from harness_dast.domain.scope_approval import ScopeApproval

_MAX_BYTES = 1024 * 1024


def file_signature(
    value: os.stat_result, *, windows: bool | None = None
) -> tuple[int, int, int, int, int]:
    """Retorna metadados de identidade; no Windows ctime pode divergir entre stat e fstat."""
    on_windows = sys.platform == "win32" if windows is None else windows
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        0 if on_windows else value.st_ctime_ns,
    )


class FileWatch:
    """Compara identidade e metadados com o arquivo cujo digest foi validado na partida."""

    def __init__(self, path: Path, digest: str, *, product: str | None = None) -> None:
        """Recusa conteúdo diferente, leitura instável e aprovação inválida quando aplicável."""
        self._path = path
        self._digest = digest
        self._signature: tuple[int, int, int, int, int] | None = None
        self._initial_failure: WatchCause | None = None
        try:
            with path.open("rb") as handle:
                before = os.fstat(handle.fileno())
                raw = handle.read(_MAX_BYTES + 1)
                after = os.fstat(handle.fileno())
            current = path.stat()
            if not stat.S_ISREG(before.st_mode) or len(raw) > _MAX_BYTES:
                self._initial_failure = WatchCause.SIZE_OR_TYPE
                return
            if file_signature(before) != file_signature(after) or file_signature(
                after
            ) != file_signature(current):
                self._initial_failure = WatchCause.UNSTABLE
                return
            if hashlib.sha256(raw).hexdigest() != digest:
                self._initial_failure = WatchCause.HASH
                return
            if product is not None and ScopeApproval.model_validate_json(raw).product != product:
                self._initial_failure = WatchCause.APPROVAL_INVALID
                return
            self._signature = file_signature(current)
        except OSError:
            self._initial_failure = WatchCause.ACCESS
        except ValidationError:
            self._initial_failure = WatchCause.APPROVAL_INVALID

    def unchanged(self) -> bool:
        """Confere metadados, falhando fechado se inacessível ou alterado."""
        return self.failure() is None

    def failure(self) -> WatchCause | None:
        """Classifica a mesma conferência, sem revelar a fonte ou os valores."""
        if self._signature is None:
            return self._initial_failure or WatchCause.DETECT_ERROR
        try:
            with self._path.open("rb") as handle:
                before = file_signature(os.fstat(handle.fileno()))
                raw = handle.read(_MAX_BYTES + 1)
                after = file_signature(os.fstat(handle.fileno()))
            if len(raw) > _MAX_BYTES:
                return WatchCause.SIZE_OR_TYPE
            if before != self._signature:
                return _signature_cause(before, self._signature)
            if after != self._signature:
                return WatchCause.UNSTABLE
            current = file_signature(self._path.stat())
            if current != after:
                return _signature_cause(current, after)
            if hashlib.sha256(raw).hexdigest() != self._digest:
                return WatchCause.HASH
        except OSError:
            return WatchCause.ACCESS
        return None


def _signature_cause(
    left: tuple[int, int, int, int, int], right: tuple[int, int, int, int, int]
) -> WatchCause:
    return WatchCause.IDENTITY if left[:2] != right[:2] else WatchCause.METADATA
