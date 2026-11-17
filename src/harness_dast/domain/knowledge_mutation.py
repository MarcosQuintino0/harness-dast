"""Chave de mutação estável sem URL, valores ou identificadores de recurso."""

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from harness_dast.domain.errors import ConfigError


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
