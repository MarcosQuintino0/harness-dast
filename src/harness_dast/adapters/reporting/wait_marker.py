"""Marcador de associação entre a trava exclusiva e a execução encadeada."""

import re
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run_ref import require_run_id

_log = structlog.get_logger()


class Marker(BaseModel):
    """Fase e identificador publicados pelo processo dono da trava."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    phase: str
    run_id: str | None = None


class FileWaitMarker:
    """Escreve e lê marcador isolado por identificador único da trava."""

    def __init__(self, runs_dir: Path, lock_id: str) -> None:
        """Recusa identificadores que não são da trava."""
        if re.fullmatch(r"[0-9a-f]{8,64}", lock_id) is None:
            raise ConfigError("Identificador da espera inválido.")
        self._path = runs_dir / f".wait-{lock_id}.json"

    def write(self, phase: str, run_id: str | None) -> None:
        """Publica atomicamente sem interromper a execução se a observação falhar."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".tmp")
            temp.write_text(Marker(phase=phase, run_id=run_id).model_dump_json(), encoding="utf-8")
            temp.replace(self._path)
        except OSError as error:
            _log.warning("wait_marker_write_failed", reason=str(error))

    def read(self) -> Marker | None:
        """Lê marcador validado; `None` quando ainda não foi criado."""
        try:
            if not self._path.exists():
                return None
            if self._path.stat().st_size > 4096:
                raise ConfigError("Marcador de espera inválido.")
            marker = Marker.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError):
            raise ConfigError("Marcador de espera inválido ou ilegível.") from None
        if marker.run_id is not None:
            require_run_id(marker.run_id)
        return marker
