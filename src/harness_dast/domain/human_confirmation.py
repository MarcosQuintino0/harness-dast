"""Contrato aditivo de confirmações humanas; não altera o relatório de achados."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.report.model import FindingsReport
from harness_dast.domain.run import SLUG_PATTERN, is_run_id


class HumanConfirmation(ApiModel):
    """Registro de quem declarou ter visto a falha, sem autenticação de identidade."""

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    person: str = Field(min_length=1, max_length=200, strict=True)
    confirmed_at: datetime
    observation: str = Field(min_length=1, max_length=2000, strict=True)

    @field_validator("confirmed_at", mode="before")
    @classmethod
    def validate_timestamp_input(cls, value: object) -> object:
        """Aceita data em texto ou datetime, sem interpretar números como timestamps."""
        if not isinstance(value, (str, datetime)):
            raise ValueError("data inválida")  # noqa: TRY004 - Pydantic converte ValueError em ValidationError.
        return value

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        """Recusa texto vazio e data sem fuso UTC."""
        if not self.person.strip() or not self.observation.strip():
            raise ValueError("texto obrigatório")
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() != UTC.utcoffset(None):
            raise ValueError("data deve estar em UTC")
        return self


class HumanConfirmations(ApiModel):
    """Envelope v1 de registros pertencentes a um produto e uma execução."""

    schema_version: Literal[1]
    product: str = Field(pattern=rf"^{SLUG_PATTERN}$", strict=True)
    run_id: str = Field(strict=True)
    entries: tuple[HumanConfirmation, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_version(cls, value: object) -> object:
        """Recusa booleanos e versões fora do contrato."""
        if type(value) is not int or value != 1:
            raise ValueError("versão inválida")
        return value

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        """Recusa identificador inválido ou incompatível com o produto."""
        if not is_run_id(self.run_id) or self.run_id[21:].rsplit("-", 1)[0] != self.product:
            raise ValueError("execução incompatível")
        return self

    def contains(self, fingerprint: str) -> bool:
        """Informa se há registro para o fingerprint nesta execução."""
        return any(entry.fingerprint == fingerprint for entry in self.entries)


def report_has_fingerprint(report: FindingsReport, fingerprint: str) -> bool:
    """Busca somente achados atuais, inclusive os estágios próprios."""
    if any(item.fingerprint == fingerprint for item in report.findings):
        return True
    return any(
        item.fingerprint == fingerprint
        for section in (report.authz, report.negative, report.proxy_signals)
        if section is not None
        for item in section.findings
    )
