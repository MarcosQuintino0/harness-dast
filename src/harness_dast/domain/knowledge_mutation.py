"""Chave de mutação estável sem URL, valores ou identificadores de recurso."""

import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from harness_dast.domain.authz.created import parse_unique_json
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.mutation_snapshot import MutationSnapshot


def mutation_key(product: str, operation: str, account: str | None, method: str) -> str:
    """Resume somente contexto da operação; mesma classe de trabalho compartilha pendência."""
    identity = json.dumps((product, operation, account, method), ensure_ascii=True)
    return hashlib.sha256(identity.encode()).hexdigest()


class MutationPending(ConfigError):
    """Uma intenção válida já está pendente para a mesma chave."""


class MutationMetadata(BaseModel):
    """Contexto não sensível da intenção, sem URL ou corpo da requisição."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    account: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    run_id: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    started_at: AwareDatetime


class PendingMutation(BaseModel):
    """Identificador e metadados disponíveis de uma intenção pendente."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: MutationMetadata | None = None


def safe_mutation_metadata(
    operation_id: str, account: str | None, method: str, run_id: str | None, started_at: datetime
) -> MutationMetadata | None:
    """Devolve metadados seguros ou omite contexto que não atende ao contrato."""
    try:
        return MutationMetadata.model_validate(
            dict(
                operation_id=operation_id,
                account=account,
                method=method,
                run_id=run_id,
                started_at=started_at,
            )
        )
    except ValidationError:
        return None


def valid_mutation_key(key: str) -> bool:
    """Confere chave hexadecimal, sem caminhos nem componentes externos."""
    return isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key) is not None


def build_mutation_intent(
    previous_state: Literal["absent", "present", "unknown"],
    snapshot: MutationSnapshot | None,
    metadata: MutationMetadata | None,
) -> dict[str, object]:
    """Valida e projeta uma inten??o sem alterar seus argumentos."""
    if previous_state not in ("absent", "present", "unknown"):
        raise ConfigError("Estado anterior de mutação inválido.")
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
    if metadata is not None:
        try:
            record["metadata"] = MutationMetadata.model_validate(metadata.model_dump()).model_dump(
                mode="json"
            )
        except (ValidationError, AttributeError):
            raise ConfigError("Metadados de mutação inválidos.") from None
    return record


def valid_mutation_intent(text: str) -> bool:
    """Diz se o registro possui formato e projeção aceitos."""
    parsed = parse_unique_json(text.encode("utf-8"))
    if not isinstance(parsed, dict) or parsed.get("intent") != "mutation":
        return False
    previous = parsed.get("previous_state")
    if previous not in ("absent", "present", "unknown"):
        return False
    if not set(parsed) <= {"intent", "previous_state", "snapshot", "metadata"}:
        return False
    try:
        if "metadata" in parsed:
            MutationMetadata.model_validate(parsed["metadata"])
        if "snapshot" in parsed:
            snapshot = MutationSnapshot.model_validate(parsed["snapshot"])
            return _matches_source(str(previous), snapshot)
    except ValidationError:
        return False
    return True


def _matches_source(previous: str, snapshot: MutationSnapshot) -> bool:
    return (snapshot.source == "observed" and previous == "present") or (
        snapshot.source == "request_baseline" and previous == "unknown"
    )
