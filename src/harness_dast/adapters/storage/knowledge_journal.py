"""Diário conservador de intenções de mutação, sem respostas ou identificadores de recurso."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from harness_dast.domain.authz_created import parse_unique_json
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.mutation_snapshot import MutationSnapshot

_KEY = re.compile(r"[0-9a-f]{64}\Z")
PreviousState = Literal["absent", "present", "unknown"]
Outcome = Literal["succeeded", "failed", "observed"]


class FileMutationJournal:
    """Grava intenção exclusiva e sincronizada antes do envio; não permite repetição cega."""

    def __init__(self, directory: Path) -> None:
        """Recebe diretório privado persistente, externo aos artefatos exportáveis."""
        self._directory = directory

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ConfigError("Chave de mutação inválida.")
        return self._directory / (key + ".jsonl")

    def begin(
        self, key: str, previous_state: PreviousState, snapshot: MutationSnapshot | None = None
    ) -> None:
        """Reserva operação antes do envio; qualquer registro existente bloqueia repetição."""
        path = self._path(key)
        if previous_state not in ("absent", "present", "unknown"):
            raise ConfigError("Estado anterior de mutação inválido.")
        record = _intent(previous_state, snapshot)
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
            raise ConfigError(
                "Já existe mutação com resultado desconhecido para esta operação e conta.",
                hint=(
                    "Confira no alvo se a mudança foi aplicada e, só depois, remova o arquivo "
                    f"pendente {path} (ação humana); o harness não repete a mutação às cegas."
                ),
            ) from None
        except OSError:
            raise self._io_error() from None

    def _io_error(self) -> ConfigError:
        return ConfigError(
            "Não foi possível gravar o diário de mutações (erro de E/S); não envie a mutação.",
            hint=f"Confira a permissão e o espaço da pasta {self._directory}.",
        )

    def finish(self, key: str, outcome: Outcome) -> None:
        """Registra resultado conhecido; falha de gravação deixa a intenção bloqueada."""
        path = self._path(key)
        if outcome not in ("succeeded", "failed", "observed"):
            raise ConfigError("Resultado de mutação inválido.")
        try:
            with path.open("r+", encoding="utf-8", newline="\n") as stream:
                lines = stream.readlines()
                if len(lines) != 1 or not _valid_intent(lines[0]):
                    raise ConfigError("Diário de mutação inválido ou já concluído.")
                stream.seek(0, os.SEEK_END)
                stream.write(json.dumps({"outcome": outcome}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            archive = self._directory / "completed" / (key + "-" + uuid.uuid4().hex + ".jsonl")
            path.rename(archive)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ConfigError("Não foi possível concluir o diário de mutação.") from None


def _intent(previous_state: PreviousState, snapshot: MutationSnapshot | None) -> dict[str, object]:
    record: dict[str, object] = {"intent": "mutation", "previous_state": previous_state}
    if snapshot is not None:
        if not isinstance(snapshot, MutationSnapshot):
            raise ConfigError("Snapshot de mutação inválido.")
        try:
            snapshot = MutationSnapshot.model_validate(snapshot.model_dump())
        except ValidationError:
            raise ConfigError("Snapshot de mutação inválido.") from None
        if not _matches_source(previous_state, snapshot):
            raise ConfigError("Origem e estado anterior da mutação são incompatíveis.")
        record["snapshot"] = snapshot.model_dump()
    return record


def _valid_intent(text: str) -> bool:
    parsed = parse_unique_json(text.encode("utf-8"))
    if not isinstance(parsed, dict) or parsed.get("intent") != "mutation":
        return False
    previous = parsed.get("previous_state")
    if previous not in ("absent", "present", "unknown"):
        return False
    if set(parsed) == {"intent", "previous_state"}:
        return True
    if set(parsed) != {"intent", "previous_state", "snapshot"}:
        return False
    try:
        snapshot = MutationSnapshot.model_validate(parsed["snapshot"])
    except ValidationError:
        return False
    return _matches_source(str(previous), snapshot)


def _matches_source(previous: str, snapshot: MutationSnapshot) -> bool:
    return (snapshot.source == "observed" and previous == "present") or (
        snapshot.source == "request_baseline" and previous == "unknown"
    )
