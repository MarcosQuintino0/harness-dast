"""Arquivo de confirmações humanas com validação e exclusão mútua entre escritores."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.human_confirmation import HumanConfirmation, HumanConfirmations
from harness_dast.domain.run_ref import require_run_id
from harness_dast.domain.strict_json import parse_strict_json


class FileHumanConfirmationStore:
    """Lê e acrescenta registros por execução; arquivo inválido interrompe a operação."""

    def __init__(self, runs_dir: Path) -> None:
        """Recebe a raiz das execuções."""
        self._runs_dir = runs_dir

    def read(self, product: str, run_id: str) -> HumanConfirmations | None:
        """Lê envelope validado, ou None quando o arquivo não existe."""
        try:
            HumanConfirmations(schema_version=1, product=product, run_id=run_id, entries=())
        except ValidationError:
            raise _invalid_file() from None
        path = self._runs_dir / require_run_id(run_id) / "human-confirmations.json"
        try:
            with path.open("rb") as handle:
                data = handle.read(8 * 1024 * 1024 + 1)
        except FileNotFoundError:
            return None
        except OSError:
            raise _invalid_file() from None
        try:
            if len(data) > 8 * 1024 * 1024:
                raise _invalid_file()
            result = HumanConfirmations.model_validate(parse_strict_json(data))
        except (ConfigError, ValueError, ValidationError):
            raise _invalid_file() from None
        if result.product != product or result.run_id != run_id:
            raise _invalid_file()
        return result

    def append(self, product: str, run_id: str, entry: HumanConfirmation) -> None:
        """Acrescenta sob trava exclusiva; concorrência ou erro não sobrescreve registros."""
        directory = self._runs_dir / require_run_id(run_id)
        lock = directory / ".human-confirmations.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            raise ConfigError(
                "Não foi possível reservar a gravação das confirmações.",
                hint="Confira a pasta e se há outra gravação em andamento.",
            ) from None
        temporary: Path | None = None
        try:
            os.close(fd)
            previous = self.read(product, run_id)
            entries = previous.entries if previous else ()
            envelope = HumanConfirmations(
                schema_version=1, product=product, run_id=run_id, entries=(*entries, entry)
            )
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as out:
                temporary = Path(out.name)
                out.write(envelope.model_dump_json(indent=2) + "\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, directory / "human-confirmations.json")
            temporary = None
        except (OSError, ValidationError):
            raise ConfigError(
                "Não foi possível gravar as confirmações.",
                hint="Confira a pasta e as permissões da execução.",
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)


def _invalid_file() -> ConfigError:
    return ConfigError(
        "Arquivo de confirmações inválido ou ilegível.",
        hint="Confira o arquivo e sua correspondência com a execução.",
    )
