"""Leitura local da execução e da trava para `wait`."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.wait_marker import FileWaitMarker
from harness_dast.application.stack_models import StackLockInfo
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.scan_result import ScanProgress
from harness_dast.domain.wait import WaitResult


class FileWaitReader:
    """Lê resultado atômico e observa trava sem alterá-la."""

    def __init__(self, runs_dir: Path, lock: Callable[[], StackLockInfo | None]) -> None:
        """Recebe pasta e consulta à trava."""
        self._runs_dir = runs_dir
        self._lock = lock
        self._artifacts = FileRunArtifacts(runs_dir)

    def read(self, run_id: str) -> WaitResult:
        """Lê estado, recusando execução ausente ou artefato inválido."""
        run_id = require_run_id(run_id)
        directory = self._runs_dir / run_id
        if not directory.is_dir():
            raise ConfigError("Execução não encontrada.", hint="Confira --run e HDAST_RUNS_DIR.")
        summary = self._artifacts.read_summary(run_id)
        if summary is not None:
            if summary.run_id != run_id:
                raise ConfigError("Identificador em run.json não corresponde à pasta.")
            return WaitResult(state="finished", status=summary.status, exit_code=summary.exit_code)
        progress = self._progress(directory, run_id)
        lock = self._lock()
        state: Literal["running", "stopped", "unknown"]
        if lock is None or lock.state == "orphan":
            # Relê após observar o processo morto, cobrindo gravação concorrente do resultado.
            summary = self._artifacts.read_summary(run_id)
            if summary is not None:
                if summary.run_id != run_id:
                    raise ConfigError("Identificador em run.json não corresponde à pasta.")
                return WaitResult(
                    state="finished", status=summary.status, exit_code=summary.exit_code
                )
            state = "stopped"
        elif lock.state == "unreadable":
            state = "unknown"
        elif (
            lock.lock_id is not None
            and (marker := FileWaitMarker(self._runs_dir, lock.lock_id).read()) is not None
            and marker.run_id == run_id
        ):
            state = "running"
        else:
            state = "unknown"
        return WaitResult(
            state=state,
            phase=progress.phase if progress else None,
            progress=progress.progress if progress else None,
        )

    def _progress(self, directory: Path, run_id: str) -> ScanProgress | None:
        path = directory / "scan-progress.json"
        try:
            if not path.exists():
                return None
            if path.stat().st_size > 1_000_000:
                raise ConfigError("Progresso da execução inválido ou ilegível.")
            progress = ScanProgress.model_validate_json(path.read_text(encoding="utf-8"))
            if progress.run_id != run_id or not 0 <= progress.progress <= 100:
                raise ConfigError("Progresso da execução inválido ou ilegível.")
        except (OSError, UnicodeError, ValueError, ValidationError):
            raise ConfigError("Progresso da execução inválido ou ilegível.") from None
        return progress


class ProductWaitReader:
    """Associa uma espera à tomada exata da trava, sem adivinhar pastas."""

    def __init__(
        self, runs_dir: Path, lock: Callable[[], StackLockInfo | None], lock_id: str | None
    ) -> None:
        """Recebe pasta, consulta à trava e eventual identificação de espera anterior."""
        self._runs_dir = runs_dir
        self._lock = lock
        self._lock_id = lock_id
        if lock_id is not None:
            FileWaitMarker(runs_dir, lock_id)
        self._files = FileRunArtifacts(runs_dir)

    def read(self, product: str) -> WaitResult:
        """Observa a tomada capturada, sem confundi-la com uma execução posterior."""
        lock = self._lock()
        if self._lock_id is None:
            if (
                lock is None
                or lock.state != "held"
                or lock.command != "run"
                or lock.product != product
            ):
                return WaitResult(state="unknown")
            self._lock_id = lock.lock_id
        if self._lock_id is None:
            return WaitResult(state="unknown")
        marker = FileWaitMarker(self._runs_dir, self._lock_id).read()
        run_id = marker.run_id if marker else None
        if run_id is not None:
            summary = self._files.read_summary(run_id)
            if summary is not None:
                if summary.run_id != run_id or summary.product != product:
                    raise ConfigError("Resultado não corresponde à espera.")
                return WaitResult(
                    state="finished",
                    status=summary.status,
                    exit_code=summary.exit_code,
                    run_id=run_id,
                    lock_id=self._lock_id,
                )
        state: Literal["running", "stopped", "unknown"]
        if lock is not None and lock.state == "unreadable":
            state = "unknown"
        elif (
            lock is not None
            and lock.state == "held"
            and lock.lock_id == self._lock_id
            and lock.product == product
        ):
            state = "running"
        else:
            state = "stopped"
        progress = (
            FileWaitReader(self._runs_dir, self._lock)._progress(self._runs_dir / run_id, run_id)
            if run_id is not None
            else None
        )
        return WaitResult(
            state=state,
            phase=marker.phase if marker else None,
            progress=progress.progress if progress and marker and marker.phase == "scan" else None,
            run_id=run_id,
            lock_id=self._lock_id,
        )
