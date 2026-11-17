"""Diário conservador de intenções de mutação, sem respostas ou identificadores de recurso."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from harness_dast.domain.authz.created import parse_unique_json
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge_mutation import (
    MutationMetadata,
    MutationPending,
    PendingMutation,
    build_mutation_intent,
    valid_mutation_intent,
    valid_mutation_key,
)
from harness_dast.domain.mutation_snapshot import MutationSnapshot

PreviousState = Literal["absent", "present", "unknown"]
Outcome = Literal["succeeded", "failed", "observed"]


class FileMutationJournal:
    """Grava intenção exclusiva e sincronizada antes do envio; não permite repetição cega."""

    def __init__(self, directory: Path) -> None:
        """Recebe diretório privado persistente, externo aos artefatos exportáveis."""
        self._directory = directory

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not valid_mutation_key(key):
            raise ConfigError("Chave de mutação inválida.")
        return self._directory / (key + ".jsonl")

    def begin(
        self,
        key: str,
        previous_state: PreviousState,
        snapshot: MutationSnapshot | None = None,
        metadata: MutationMetadata | None = None,
    ) -> None:
        """Reserva operação antes do envio; qualquer registro existente bloqueia repetição."""
        path = self._path(key)
        if previous_state not in ("absent", "present", "unknown"):
            raise ConfigError("Estado anterior de mutação inválido.")
        record = build_mutation_intent(previous_state, snapshot, metadata)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            (self._directory / "completed").mkdir(exist_ok=True)
        except OSError:
            raise self._io_error() from None
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            self._read_pending(path)
            raise MutationPending(
                "Já existe mutação com resultado desconhecido para esta operação e conta.",
                hint="Peça a uma pessoa para conferir o alvo e executar hdast mutation release "
                + key,
            ) from None
        except OSError:
            raise self._io_error() from None

    def _io_error(self) -> ConfigError:
        return ConfigError(
            "Não foi possível gravar o diário de mutações (erro de E/S); não envie a mutação.",
            hint=f"Confira a permissão e o espaço da pasta {self._directory}.",
        )

    def list_pending(self) -> tuple[PendingMutation, ...]:
        """Lista intenções válidas; registros corrompidos interrompem a leitura."""
        try:
            paths = sorted(path for path in self._directory.iterdir() if path.suffix == ".jsonl")
            return tuple(self._read_pending(path) for path in paths)
        except FileNotFoundError:
            if not self._directory.exists():
                return ()
            raise ConfigError("Não foi possível ler o diário de mutações.") from None
        except OSError:
            raise ConfigError("Não foi possível ler o diário de mutações.") from None

    def _read_pending(self, path: Path) -> PendingMutation:
        self._path(path.stem)
        try:
            if path.is_symlink():
                raise ConfigError("Diário de mutação inválido.")
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) != 1 or not valid_mutation_intent(lines[0]):
                raise ConfigError("Diário de mutação inválido ou já concluído.")
            parsed = parse_unique_json(lines[0].encode("utf-8"))
            if not isinstance(parsed, dict):
                raise ConfigError("Diário de mutação inválido.")
            metadata = (
                MutationMetadata.model_validate(parsed["metadata"])
                if "metadata" in parsed
                else None
            )
            return PendingMutation(id=path.stem, metadata=metadata)
        except (OSError, UnicodeError, ValidationError, ValueError):
            raise ConfigError("Não foi possível ler diário de mutação válido.") from None

    def release(self, key: str, released_at: datetime) -> None:
        """Registra liberação humana e arquiva; não inspeciona nem toca o alvo."""
        self._read_pending(self._path(key))
        self._finish(key, "human_release", released_at)

    def finish(self, key: str, outcome: Outcome) -> None:
        """Registra resultado conhecido; falha de gravação deixa a intenção bloqueada."""
        if outcome not in ("succeeded", "failed", "observed"):
            raise ConfigError("Resultado de mutação inválido.")
        self._finish(key, outcome)

    def _finish(self, key: str, outcome: str, released_at: datetime | None = None) -> None:
        path = self._path(key)
        try:
            (self._directory / "completed").mkdir(exist_ok=True)
            with path.open("r+", encoding="utf-8", newline="\n") as stream:
                lines = stream.readlines()
                if len(lines) != 1 or not valid_mutation_intent(lines[0]):
                    raise ConfigError("Diário de mutação inválido ou já concluído.")
                stream.seek(0, os.SEEK_END)
                result = {"outcome": outcome}
                if released_at is not None:
                    result["event"] = "mutation_human_release"
                    result["released_at"] = released_at.isoformat()
                stream.write(json.dumps(result) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            archive = self._directory / "completed" / (key + "-" + uuid.uuid4().hex + ".jsonl")
            path.rename(archive)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ConfigError("Não foi possível concluir o diário de mutação.") from None
