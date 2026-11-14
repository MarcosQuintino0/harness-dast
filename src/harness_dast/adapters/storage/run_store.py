"""Armazém dos arquivos de uma execução em `<runs_dir>/<run_id>/` (implementa `RunStore`).

- `audit.jsonl`: só acréscimo; cada linha é gravada e enviada ao disco (`fsync`) antes de a
  chamada retornar, para que a decisão registrada exista mesmo se o processo morrer logo
  depois do envio.
- `manifest.json` e `probe.json`: gravados por arquivo temporário e `os.replace`, para nunca
  existir um arquivo pela metade.

O `run_id` é revalidado (`RunId`) antes de virar nome de pasta: não há como escapar de
`runs_dir`. Falhas de escrita viram `ConfigError`.
"""

import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_exchange import ExchangeLog
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.run import RunId

AUDIT_FILE = "audit.jsonl"
MANIFEST_FILE = "manifest.json"
PROBE_FILE = "probe.json"
EXCHANGES_FILE = "exchanges.json"


class FileRunStore:
    """Grava os arquivos de cada execução no sistema de arquivos."""

    def __init__(self, runs_dir: Path) -> None:
        """Cria o armazém.

        Args:
            runs_dir: Pasta das execuções (`HDAST_RUNS_DIR`); é criada se não existir.
        """
        self._runs_dir = runs_dir

    def write_manifest(self, run_id: str, manifest: RunManifest) -> None:
        """Grava `manifest.json` de forma atômica."""
        self._write_json(run_id, MANIFEST_FILE, manifest)

    def write_probe(self, run_id: str, result: ProbeResult) -> None:
        """Grava `probe.json` de forma atômica."""
        self._write_json(run_id, PROBE_FILE, result)

    def write_exchanges(self, run_id: str, log: ExchangeLog) -> None:
        """Grava `exchanges.json` de forma atômica."""
        self._write_json(run_id, EXCHANGES_FILE, log)

    def append_audit(self, run_id: str, entry: AuditEntry) -> None:
        """Acrescenta uma linha a `audit.jsonl` e a persiste antes de retornar."""
        path = self._directory(run_id) / AUDIT_FILE
        line = entry.model_dump_json() + "\n"
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            raise _write_error(AUDIT_FILE) from None

    def _directory(self, run_id: str) -> Path:
        try:
            valid = RunId(value=run_id)
        except ValidationError:
            raise ConfigError(
                "Identificador de execução inválido.", hint="Use o run_id devolvido pelo comando."
            ) from None
        directory = self._runs_dir / valid.value
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise _write_error("a pasta da execução") from None
        return directory

    def _write_json(self, run_id: str, name: str, model: BaseModel) -> None:
        directory = self._directory(run_id)
        target = directory / name
        temporary = directory / f".{name}.tmp"
        try:
            temporary.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, target)
        except OSError:
            raise _write_error(name) from None


def _write_error(what: str) -> ConfigError:
    return ConfigError(
        f"Não foi possível gravar {what} da execução.",
        hint="Confira HDAST_RUNS_DIR, o espaço em disco e a permissão de escrita.",
    )
