"""Diário conservador de intenções de mutação, sem respostas ou identificadores de recurso."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal

from harness_dast.domain.errors import ConfigError

_KEY = re.compile(r"[0-9a-f]{64}\Z")
PreviousState = Literal["absent", "present", "unknown"]
Outcome = Literal["succeeded", "failed"]


class FileMutationJournal:
    """Grava intenção exclusiva e sincronizada antes do envio; não permite repetição cega."""

    def __init__(self, directory: Path) -> None:
        """Recebe diretório privado persistente, externo aos artefatos exportáveis."""
        self._directory = directory

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ConfigError("Chave de mutação inválida.")
        return self._directory / (key + ".jsonl")

    def begin(self, key: str, previous_state: PreviousState) -> None:
        """Reserva operação antes do envio; qualquer registro existente bloqueia repetição."""
        path = self._path(key)
        if previous_state not in ("absent", "present", "unknown"):
            raise ConfigError("Estado anterior de mutação inválido.")
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            (self._directory / "completed").mkdir(exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    json.dumps({"intent": "mutation", "previous_state": previous_state}) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            raise ConfigError(
                "Não foi possível registrar a intenção; não envie a mutação."
            ) from None

    def finish(self, key: str, outcome: Outcome) -> None:
        """Registra resultado conhecido; falha de gravação deixa a intenção bloqueada."""
        path = self._path(key)
        if outcome not in ("succeeded", "failed"):
            raise ConfigError("Resultado de mutação inválido.")
        try:
            with path.open("r+", encoding="utf-8", newline="\n") as stream:
                lines = stream.readlines()
                if len(lines) != 1 or json.loads(lines[0]) not in (
                    {"intent": "mutation", "previous_state": "absent"},
                    {"intent": "mutation", "previous_state": "present"},
                    {"intent": "mutation", "previous_state": "unknown"},
                ):
                    raise ConfigError("Diário de mutação inválido ou já concluído.")
                stream.seek(0, os.SEEK_END)
                stream.write(json.dumps({"outcome": outcome}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            archive = self._directory / "completed" / (key + "-" + uuid.uuid4().hex + ".jsonl")
            path.rename(archive)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ConfigError("Não foi possível concluir o diário de mutação.") from None
