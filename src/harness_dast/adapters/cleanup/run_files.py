"""Arquivos de limpeza de uma execução em `<runs_dir>/<run_id>/` (implementa `CleanupRuns`).

- `manifest.json`: só leitura aqui (quem escreve é o `probe`).
- `cleanup.json`: gravado de forma atômica.
- `cleanup-audit.jsonl`: só acréscimo, com `fsync` a cada linha.
- `cleanup-confirmation.json`: o token pendente (SÓ o hash). Gastar o token é um `os.replace`
  do arquivo para outro nome: dois processos concorrentes nunca gastam o mesmo token.

O `run_id` é revalidado (`RunId`) antes de virar nome de pasta. A pasta da execução nunca é
criada aqui: uma execução que não existe é um erro, não algo a inventar.
"""

import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from harness_dast.domain.cleanup_confirmation import ConfirmationRecord
from harness_dast.domain.cleanup_plan import CleanupAuditLine, CleanupRecord
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_result import RunManifest
from harness_dast.domain.run import RunId

MANIFEST_FILE = "manifest.json"
RECORD_FILE = "cleanup.json"
AUDIT_FILE = "cleanup-audit.jsonl"
CONFIRMATION_FILE = "cleanup-confirmation.json"
CONFIRMATION_USED_FILE = "cleanup-confirmation.used.json"
_MAX_MANIFEST_BYTES = 256 * 1024


def _write_error(what: str) -> ConfigError:
    return ConfigError(
        f"Não foi possível gravar {what} da execução.",
        hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
    )


class FileCleanupRuns:
    """Lê o manifesto e grava os arquivos de limpeza de cada execução."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o adaptador.

        Args:
            runs_dir: Pasta das execuções (`HDAST_RUNS_DIR`).
        """
        self._runs_dir = runs_dir

    def read_manifest(self, run_id: str) -> RunManifest | None:
        """Lê `manifest.json`; `None` se a execução não existe."""
        path = self._directory(run_id) / MANIFEST_FILE
        try:
            with path.open("rb") as handle:
                raw = handle.read(_MAX_MANIFEST_BYTES + 1)
        except FileNotFoundError:
            return None
        except OSError:
            raise ConfigError(
                "Não foi possível ler o manifesto da execução.",
                hint="Confira a permissão de leitura de HDAST_RUNS_DIR.",
            ) from None
        try:
            if len(raw) > _MAX_MANIFEST_BYTES:
                raise ValueError("manifesto grande demais")  # noqa: TRY301 - mesma resposta abaixo
            return RunManifest.model_validate_json(raw)
        except ValueError:
            raise ConfigError(
                "O manifesto da execução é inválido.",
                hint="Não edite manifest.json; use um run_id gerado pelo probe.",
            ) from None

    def write_record(self, run_id: str, record: CleanupRecord) -> None:
        """Grava `cleanup.json` de forma atômica."""
        self._write_json(run_id, RECORD_FILE, record)

    def append_audit(self, run_id: str, line: CleanupAuditLine) -> None:
        """Acrescenta uma linha a `cleanup-audit.jsonl` e a persiste antes de retornar."""
        path = self._directory(run_id) / AUDIT_FILE
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line.model_dump_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            raise _write_error(AUDIT_FILE) from None

    def save_confirmation(self, run_id: str, record: ConfirmationRecord) -> None:
        """Guarda o token pendente (só o hash), substituindo o anterior."""
        self._write_json(run_id, CONFIRMATION_FILE, record)

    def load_confirmation(self, run_id: str) -> ConfirmationRecord | None:
        """Lê o token pendente; arquivo ausente ou ilegível vale como "não há token"."""
        path = self._directory(run_id) / CONFIRMATION_FILE
        try:
            return ConfirmationRecord.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None

    def consume_confirmation(self, run_id: str) -> bool:
        """Gasta o token: renomeia o arquivo de forma atômica; só um chamador consegue."""
        directory = self._directory(run_id)
        try:
            os.replace(directory / CONFIRMATION_FILE, directory / CONFIRMATION_USED_FILE)
        except OSError:
            return False
        return True

    def _directory(self, run_id: str) -> Path:
        try:
            valid = RunId(value=run_id)
        except ValidationError:
            raise ConfigError(
                "Identificador de execução inválido.", hint="Use o run_id devolvido pelo probe."
            ) from None
        return self._runs_dir / valid.value

    def _write_json(self, run_id: str, name: str, model: BaseModel) -> None:
        directory = self._directory(run_id)
        temporary = directory / f".{name}.tmp"
        try:
            temporary.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, directory / name)
        except OSError:
            raise _write_error(name) from None
