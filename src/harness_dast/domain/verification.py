"""Contrato e classificação conservadora de verificação, sem acesso ao alvo."""

import re
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding
from harness_dast.domain.run import SLUG_PATTERN, is_run_id

VerificationLevel = Literal[
    "reproduced", "likely", "inconclusive", "likely_false_positive", "not_verifiable"
]


class VerificationEntry(ApiModel):
    """Resultado aditivo de um achado; evidências são textos redigidos pelo produtor."""

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    level: VerificationLevel
    reason: str = Field(min_length=1, max_length=500)
    recipe: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    attack: str | None = Field(default=None, max_length=2000)
    control: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        """Recusa motivo composto apenas por espaços."""
        if not value.strip():
            raise ValueError("motivo vazio")
        return value


class VerificationFile(ApiModel):
    """Envelope v1; exige identificação coerente e um resultado por fingerprint."""

    schema_version: Literal[1]
    product: str = Field(pattern=rf"^{SLUG_PATTERN}$")
    run_id: str
    entries: tuple[VerificationEntry, ...] = Field(max_length=5000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        """Recusa booleano e coerção de tipos para a versão do envelope."""
        if type(value) is not int:
            raise ValueError("versão inválida")
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Recusa execução inválida, produto divergente ou fingerprints repetidos."""
        if not is_run_id(self.run_id) or not re.fullmatch(
            rf".{{20}}-{re.escape(self.product)}-[0-9a-f]{{4,8}}", self.run_id
        ):
            raise ValueError("identificação de execução inválida")
        if len({entry.fingerprint for entry in self.entries}) != len(self.entries):
            raise ValueError("fingerprint repetido")
        return self


def parse_verification(data: object) -> VerificationFile:
    """Valida envelope externo; falhas não incluem valores ou caminhos fornecidos.

    Raises:
        ConfigError: Quando o envelope é inválido ou incompleto.
    """
    try:
        return VerificationFile.model_validate(data)
    except ValidationError:
        raise ConfigError(
            "verification.json inválido.", hint="Confira o envelope e seus campos obrigatórios."
        ) from None


def classify_finding(finding: Finding) -> VerificationEntry:
    """Classifica apenas evidência guardada; nunca declara reprodução nem prova contrária."""
    evidence = finding.evidence
    flagged = finding.proposed_confidence == "false_positive"
    if flagged:
        level: VerificationLevel = "not_verifiable"
        reason = "O ZAP indicou falso positivo; o indício exige revisão humana."
    elif evidence.available and evidence.zap_evidence.strip():
        level = "likely"
        reason = "O ZAP apontou um trecho de evidência guardada; falta reprodução."
    else:
        level = "not_verifiable"
        reason = "Não há trecho de prova disponível; a ausência não refuta o alerta."
    return VerificationEntry(fingerprint=finding.fingerprint, level=level, reason=reason)
