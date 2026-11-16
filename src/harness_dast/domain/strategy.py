"""Estratégia versionada: referências e declaração fechada de preservação da cobertura."""

from datetime import UTC, date, datetime
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.strategy_basis import StrategyBasis
from harness_dast.domain.window import ensure_aware

_HINT = "Corrija strategy.yml conforme o contrato da estratégia."


class StrategyReferences(ProfileModel):
    """Caminhos relativos dos três documentos existentes do produto."""

    target: Literal["target.yml"]
    data_rules: Literal["data-rules.yml"]
    flows: Literal["flows.yml"]


class CoverageChoice(ProfileModel):
    """Declaração tipada de preservação; origem observada nunca concede permissão."""

    name: Literal["coverage"]
    value: Literal["preserve"]
    source: Literal["owner", "contract", "observation"]
    reason: Literal["preserve_baseline"]
    valid_until: date
    state: Literal["proposed", "validated", "review_required"]
    basis: StrategyBasis | None = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> object:
        """Aceita data explícita, sem timestamps ou números ambíguos."""
        if type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("validade deve ser uma data ISO")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("validade deve ser uma data ISO") from None
        if parsed.isoformat() != value:
            raise ValueError("validade deve ser uma data ISO")
        return parsed


class Strategy(ProfileModel):
    """Estratégia congelada; nenhuma escolha autoriza mudança do perfil."""

    schema_version: Literal[1]
    references: StrategyReferences
    choices: tuple[CoverageChoice, ...] = Field(max_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        """Exige inteiro, sem coerção de booleano."""
        if type(value) is not int or value != 1:
            raise ValueError("versão não suportada")
        return value

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Valida dados externos sem reproduzir chaves ou valores potencialmente secretos."""
        try:
            return cls.model_validate(data)
        except ValidationError:
            raise ConfigError("Estratégia inválida.", hint=_HINT) from None

    def ensure_metadata_valid(self, now: datetime) -> None:
        """Confere estado e validade para preparação; não autoriza qualquer envio."""
        ensure_aware(now)
        if any(
            choice.state != "validated" or choice.valid_until < now.astimezone(UTC).date()
            for choice in self.choices
        ):
            raise ConfigError("Estratégia pendente ou vencida.", hint=_HINT)

    def ensure_compilable(self, now: datetime, basis: StrategyBasis | None = None) -> None:
        """Confere estado, validade e vínculo atual; não concede aprovação por si só."""
        self.ensure_metadata_valid(now)
        if any(
            basis is None or choice.basis is None or choice.basis != basis
            for choice in self.choices
        ):
            raise ConfigError("Vínculo da estratégia indisponível ou alterado.", hint=_HINT)
