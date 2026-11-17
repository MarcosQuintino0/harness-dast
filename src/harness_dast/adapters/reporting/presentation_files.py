"""Leitor de arquivos consultivos, sem rede e sem escrita."""

import json
from pathlib import Path

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.human_confirmation import HumanConfirmations
from harness_dast.domain.report.presentation import Calibration, parse_calibration
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.verification import VerificationFile, parse_verification

_MAX_BYTES = 8 * 1024 * 1024


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("chave duplicada")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("constante inválida")


def _read(path: Path) -> object | None:
    try:
        with path.open("rb") as stream:
            data = stream.read(_MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ConfigError(
            "Arquivo consultivo inválido ou ilegível.", hint="Confira o arquivo."
        ) from None
    if len(data) > _MAX_BYTES:
        raise ConfigError("Arquivo consultivo grande demais.", hint="Confira o arquivo.")
    try:
        result: object = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise ConfigError("Arquivo consultivo inválido.", hint="Confira o arquivo.") from None
    if result is None:
        raise ConfigError("Arquivo consultivo nulo.", hint="Confira o arquivo.")
    return result


class FilePresentationFiles:
    """Lê entradas opcionais, recusando conteúdo inválido e identidade divergente."""

    def __init__(self, runs_dir: Path, calibration_path: Path) -> None:
        """Recebe raiz das execuções e caminho explícito da calibração."""
        self._runs_dir = runs_dir
        self._calibration_path = calibration_path

    def verification(self, product: str, run_id: str) -> VerificationFile | None:
        """Lê verificação da execução; ausência devolve None."""
        data = _read(self._runs_dir / require_run_id(run_id) / "verification.json")
        return None if data is None else parse_verification(data)

    def confirmations(self, product: str, run_id: str) -> HumanConfirmations | None:
        """Lê confirmações da execução; ausência devolve None."""
        data = _read(self._runs_dir / require_run_id(run_id) / "human-confirmations.json")
        if data is None:
            return None
        try:
            result = HumanConfirmations.model_validate(data)
        except ValidationError:
            raise ConfigError("Confirmações inválidas.", hint="Confira o arquivo.") from None
        if result.product != product or result.run_id != run_id:
            raise ConfigError("Confirmações de outra execução.", hint="Confira produto e run_id.")
        return result

    def calibration(self) -> Calibration | None:
        """Lê calibração; ausência devolve None."""
        data = _read(self._calibration_path)
        return None if data is None else parse_calibration(data)
