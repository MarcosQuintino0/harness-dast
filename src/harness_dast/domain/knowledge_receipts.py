"""Recibos estruturais de decisões aplicadas no probe, sem valores gerados."""

from typing import Literal

from pydantic import Field

from harness_dast.domain.secret_ref import ProfileModel

_NAME = r"^[A-Za-z_][A-Za-z0-9_.-]{0,199}$"
_FIELD = r"^[A-Za-z_][A-Za-z0-9_.-]{0,199}$"


class KnowledgeRuleUse(ProfileModel):
    """Regra efetivamente usada na montagem de uma requisição bem-sucedida."""

    operation: str = Field(pattern=_NAME)
    rule_index: int = Field(ge=0, le=499, strict=True)
    generator: str = Field(pattern=_NAME)
    field: str = Field(pattern=_FIELD)
    location: Literal["path", "query", "header", "cookie", "body"]


class KnowledgeFlowUse(ProfileModel):
    """Vínculo resolvido entre operações, sem guardar o valor encadeado."""

    producer: str = Field(pattern=_NAME)
    consumer: str = Field(pattern=_NAME)
    source_field: str = Field(pattern=_FIELD)
    target_kind: Literal["param", "field"]
    target_field: str = Field(pattern=_FIELD)
