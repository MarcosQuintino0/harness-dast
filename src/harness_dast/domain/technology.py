"""Declaração consultiva de tecnologias, sem efeito sobre a varredura (ADR 0068)."""

import re
from typing import Literal

from pydantic import Field, field_validator

from harness_dast.domain.secret_ref import ProfileModel


class TechnologyDeclaration(ProfileModel):
    """Tecnologias citadas na carta e a frase que as sustenta; não confere sua veracidade."""

    value: tuple[str, ...] = Field(min_length=1, max_length=20)
    source: Literal["carta"]
    quote: str = Field(min_length=1, max_length=300)

    @field_validator("value")
    @classmethod
    def validate_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Exige identificadores únicos e normalizados, sem interpretar sua semântica."""
        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[a-z0-9][a-z0-9._+-]{0,63}", name) for name in value
        ):
            raise ValueError("use identificadores únicos em minúsculas")
        return tuple(sorted(value))

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, value: str) -> str:
        """Exige frase não vazia e imprimível."""
        if not value.strip() or not value.isprintable():
            raise ValueError("informe uma frase imprimível da carta")
        return value
