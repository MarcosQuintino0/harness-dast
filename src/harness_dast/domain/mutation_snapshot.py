"""Projeção mínima e conservadora de campo escalar anterior a uma mutação."""

import math
import re
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, ValidationError, field_validator

from harness_dast.domain.api_schema import ApiModel, JsonValue
from harness_dast.domain.authz_config import normalize_field_name
from harness_dast.domain.authz_fields import AUDIT_NAMES, classify_candidate
from harness_dast.domain.authz_sensitive import classify_field_name

_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SAFE_KINDS = frozenset({"privilege", "balance", "price", "state"})
_MAX_ABS = 1_000_000_000


class MutationSnapshot(ApiModel):
    """Somente um campo reconhecido e escalar limitado; não contém recurso nem resposta inteira."""

    field: str = Field(min_length=1, max_length=64)
    value: StrictBool | StrictInt | StrictFloat = Field(repr=False)
    source: Literal["observed", "request_baseline"]

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        """Recusa segredos, identificadores e campos de significado desconhecido."""
        normalized = normalize_field_name(value)
        if (
            not _FIELD.fullmatch(value)
            or normalized in AUDIT_NAMES
            or normalized.endswith("id")
            or classify_field_name(value) != "plain"
            or classify_candidate(value) not in _SAFE_KINDS
        ):
            raise ValueError("campo não elegível para snapshot")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: bool | int | float) -> bool | int | float:
        """Recusa números não finitos ou fora do limite para o diário privado."""
        if abs(value) > _MAX_ABS or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError("escalar fora dos limites do diário")
        return value


def project_snapshot(
    field: str,
    value: JsonValue,
    source: Literal["observed", "request_baseline"],
    *,
    forbidden: frozenset[str] = frozenset(),
) -> MutationSnapshot | None:
    """Projeta campo seguro ou devolve `None`, sem ecoar dado rejeitado."""
    if normalize_field_name(field) in {normalize_field_name(item) for item in forbidden}:
        return None
    if not isinstance(value, bool | int | float):
        return None
    try:
        return MutationSnapshot(field=field, value=value, source=source)
    except ValidationError:
        return None
