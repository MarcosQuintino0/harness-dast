"""Visão consultiva dos achados, independente do contrato de findings.json."""

from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.human_confirmation import HumanConfirmation
from harness_dast.domain.verification import VerificationEntry


class CalibrationMeasurement(ApiModel):
    """Resultado medido por tipo e critério, com amostra e proveniência."""

    finding_type: str = Field(min_length=1, max_length=200, strict=True)
    criterion: str = Field(min_length=1, max_length=200, strict=True)
    correct: int = Field(ge=0, strict=True)
    sample: int = Field(ge=1, strict=True)
    provenance: str = Field(min_length=1, max_length=500, strict=True)

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        """Recusa contagens impossíveis e campos textuais vazios."""
        if self.correct > self.sample or not all(
            x.strip() for x in (self.finding_type, self.criterion, self.provenance)
        ):
            raise ValueError("medição inválida")
        return self


class Calibration(ApiModel):
    """Envelope de calibração; bloqueio não representa amostra zero."""

    schema_version: Literal[1]
    status: Literal["blocked", "measured"]
    provenance: str = Field(min_length=1, max_length=500, strict=True)
    measurements: tuple[CalibrationMeasurement, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        """Recusa coerção da versão, inclusive booleanos."""
        if type(value) is not int:
            raise ValueError("versão inválida")
        return value

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        """Recusa estado incompatível com as medições."""
        if not self.provenance.strip() or (self.status == "blocked") != (not self.measurements):
            raise ValueError("estado inválido")
        return self


def parse_calibration(data: object) -> Calibration:
    """Valida calibração externa, sem ecoar entrada em erros.

    Raises:
        ConfigError: Formato ou valores inválidos.
    """
    try:
        return Calibration.model_validate(data)
    except ValidationError:
        raise ConfigError("Calibração inválida.", hint="Confira o arquivo de calibração.") from None


class PresentedFinding(ApiModel):
    """Um achado atual com classificação e registros humanos consultivos."""

    finding_id: str
    title: str
    severity: str
    origin: Literal["zap", "authz", "negative", "proxy"]
    verification: VerificationEntry
    confirmations: tuple[HumanConfirmation, ...] = ()

    @property
    def needs_person(self) -> bool:
        """Seleciona inconclusivos e graves sem reprodução automática."""
        return self.verification.level == "inconclusive" or (
            self.severity == "high" and self.verification.level != "reproduced"
        )


class Presentation(ApiModel):
    """Dados para visualização, sem modificar o relatório de achados."""

    findings: tuple[PresentedFinding, ...]
    calibration: Calibration | None = None


def calibration_text(item: CalibrationMeasurement) -> str | None:
    """Mostra proporção medida somente com pelo menos dez observações."""
    if item.sample < 10:
        return None
    percent = 100 * item.correct / item.sample
    return (
        f"No laboratório, {item.correct} de {item.sample} ({percent:.1f}%) — "
        f"{item.finding_type}; {item.criterion}; amostra {item.sample}; {item.provenance}."
    )
