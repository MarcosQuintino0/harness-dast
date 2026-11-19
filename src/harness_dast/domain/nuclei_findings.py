"""Projeção de resultados JSONL do Nuclei e interpretação de achados (ADR 0122)."""

import hashlib
import json
from collections.abc import Iterable
from typing import Annotated, Final, Literal, Self

from pydantic import (
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from harness_dast.domain.errors import ExternalToolError, ScopeViolation
from harness_dast.domain.nuclei_manifest import NucleiSeverity
from harness_dast.domain.profile_errors import describe_problems, format_location
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.urlnorm import normalize_request, split_request
from harness_dast.domain.zap_alert import SEVERITY_RANK, Severity

__all__ = [
    "NUCLEI_FINGERPRINT_VERSION",
    "NucleiFinding",
    "NucleiResultRecord",
    "TechnologyDetected",
    "classify",
    "group_findings",
    "parse_nuclei_jsonl",
]

NUCLEI_FINGERPRINT_VERSION: Final = 1
"""Versão da sequência de campos codificada na impressão digital."""

_SEVERITY: Final[dict[NucleiSeverity, Severity]] = {
    "critical": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "informational",
    "unknown": "informational",
}
_DETECTION_TYPES = frozenset({"detection", "technology"})
_RESULT_FIELDS = (
    ("template-id", "template_id"),
    ("template-path", "template_path"),
    ("type", "type"),
    ("host", "host"),
    ("method", "method"),
    ("matched-at", "matched_path"),
    ("matcher-name", "matcher_name"),
)
_NonEmpty = Annotated[str, StringConstraints(min_length=1)]
_Label = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")]
_Method = Annotated[str, StringConstraints(pattern=r"^[!#$%&'*+.^_`|~0-9A-Z-]+$")]


class NucleiResultRecord(ProfileModel):
    """Metadados de uma linha JSONL após o descarte de conteúdo bruto.

    `host` guarda a autoridade canônica e `matched_path` guarda só o caminho normalizado.
    `method` pode ser ausente na saída do motor. Os valores extraídos fornecem somente
    a contagem e o tamanho total em bytes UTF-8.
    """

    template_id: _Label
    template_path: _NonEmpty
    severity: NucleiSeverity
    type: _Label
    host: _NonEmpty
    method: _Method | None = None
    matched_path: _NonEmpty
    matcher_name: _NonEmpty | None = None
    extracted_count: Annotated[StrictInt, Field(ge=0)] = 0
    extracted_bytes: Annotated[StrictInt, Field(ge=0)] = 0

    @classmethod
    def from_data(cls, data: object) -> Self:
        """Projeta um objeto JSON já lido, descartando chaves fora da lista branca.

        Raises:
            ExternalToolError: O dado não é um objeto ou um metadado falhou na validação.
        """
        if not isinstance(data, dict):
            raise ExternalToolError("Linha JSONL do Nuclei deve conter um objeto JSON.")
        fields: dict[str, object] = data
        projected: dict[str, object] = {
            field: fields[source] for source, field in _RESULT_FIELDS if source in fields
        }
        projected["severity"] = _project_severity(fields.get("info", {}))
        extracted_count, extracted_bytes = _summarize_extracted(fields.get("extracted-results"))
        projected.update(extracted_count=extracted_count, extracted_bytes=extracted_bytes)
        try:
            return cls.model_validate(projected)
        except ValidationError as error:
            problems = ". ".join(
                f"{format_location(location)} ({problem})"
                for location, problem in describe_problems(error)
            )
            raise ExternalToolError(f"Linha JSONL do Nuclei inválida. {problems}.") from None

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Conserva só o host e a porta, sem credenciais, caminho, consulta ou fragmento."""
        location = _without_query(value)
        if "://" not in location:
            location = f"https://{location}"
        try:
            parts = split_request("GET", location)
        except ScopeViolation:
            raise ValueError("host HTTP(S) inválido") from None
        authority = location.split("://", 1)[1].partition("/")[0]
        explicit_port = f":{parts.port}"
        return parts.host.text + (explicit_port if authority.endswith(explicit_port) else "")

    @field_validator("matched_path")
    @classmethod
    def validate_matched_path(cls, value: str) -> str:
        """Canonicaliza o caminho e descarta a origem, a consulta e o fragmento."""
        location = _without_query(value)
        if location.startswith("/"):
            location = "https://result.invalid" + location
        try:
            normalized = normalize_request("GET", location)
        except ScopeViolation:
            raise ValueError("matched_path precisa indicar um caminho HTTP(S) válido") from None
        return normalized.url.removeprefix(normalized.origin)

    @field_validator("template_path")
    @classmethod
    def validate_template_path(cls, value: str) -> str:
        """Aceita um caminho de arquivo, sem URL, consulta ou controles."""
        if not value.isprintable() or any(marker in value for marker in ("://", "?", "#")):
            raise ValueError("template_path deve ser um caminho de arquivo")
        return value

    @model_validator(mode="after")
    def validate_matcher_name(self) -> Self:
        """Recusa caracteres não imprimíveis no nome do verificador."""
        if self.matcher_name is not None and not self.matcher_name.isprintable():
            raise ValueError("matcher_name deve conter apenas caracteres imprimíveis")
        return self


class NucleiFinding(ProfileModel):
    """Achado identificado pela impressão digital estável do resultado."""

    origin: Literal["nuclei"] = "nuclei"
    finding_id: str
    fingerprint: str
    record: NucleiResultRecord
    proposed_severity: Severity
    occurrences: Annotated[StrictInt, Field(ge=1)] = 1


class TechnologyDetected(ProfileModel):
    """Detecção informativa de uma tecnologia, sem impacto na contagem de achados."""

    record: NucleiResultRecord


def parse_nuclei_jsonl(line: str) -> NucleiResultRecord:
    """Interpreta uma única linha JSONL e valida apenas a projeção.

    Raises:
        ExternalToolError: Linha malformada, campo obrigatório ausente ou metadado
            inválido. O erro indica o campo sem reproduzir dados recebidos.
    """
    try:
        data: object = json.loads(line)
    except (ValueError, RecursionError):
        raise ExternalToolError("Linha JSONL do Nuclei malformada.") from None
    return NucleiResultRecord.from_data(data)


def _project_severity(info: object) -> object:
    if not isinstance(info, dict):
        raise ExternalToolError("Campo info da linha JSONL do Nuclei deve ser um objeto.")
    fields: dict[str, object] = info
    value = fields.get("severity", "unknown")
    return "unknown" if isinstance(value, str) and value not in _SEVERITY else value


def _summarize_extracted(values: object) -> tuple[int, int]:
    if values is None:
        return 0, 0
    if not isinstance(values, list):
        raise ExternalToolError(
            "Campo extracted-results da linha JSONL deve ser uma lista de textos."
        )
    extracted: list[object] = values
    total = 0
    for value in extracted:
        if not isinstance(value, str):
            raise ExternalToolError("Campo extracted-results contém um item que não é texto.")
        total += _count_utf8_bytes(value)
    return len(extracted), total


def _count_utf8_bytes(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ExternalToolError("Campo extracted-results contém texto inválido em UTF-8.") from None


def _without_query(value: str) -> str:
    return value.split("#", 1)[0].split("?", 1)[0]


def _fingerprint(record: NucleiResultRecord) -> str:
    parts = (
        f"hdast-nuclei-v{NUCLEI_FINGERPRINT_VERSION}",
        record.template_id,
        record.method or "",
        record.matched_path,
    )
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify(record: NucleiResultRecord) -> NucleiFinding | TechnologyDetected:
    """Classifica uma detecção informativa de tecnologia ou constrói um achado."""
    severity = _SEVERITY[record.severity]
    path = "/" + record.template_path.replace("\\", "/")
    is_detection = record.type in _DETECTION_TYPES or "/http/technologies/" in path
    if severity == "informational" and is_detection:
        return TechnologyDetected(record=record)
    fingerprint = _fingerprint(record)
    return NucleiFinding(
        finding_id=f"U-{fingerprint[:8]}",
        fingerprint=fingerprint,
        record=record,
        proposed_severity=severity,
    )


def group_findings(findings: Iterable[NucleiFinding]) -> tuple[NucleiFinding, ...]:
    """Soma ocorrências por impressão digital e conserva a observação mais grave.

    Achados saem em ordem de impressão digital. Em empate de severidade prevalece a
    primeira observação da entrada.
    """
    by_fingerprint: dict[str, NucleiFinding] = {}
    for finding in findings:
        previous = by_fingerprint.get(finding.fingerprint)
        if previous is None:
            by_fingerprint[finding.fingerprint] = finding
            continue
        representative = max(
            previous, finding, key=lambda item: SEVERITY_RANK[item.proposed_severity]
        )
        by_fingerprint[finding.fingerprint] = representative.model_copy(
            update={"occurrences": previous.occurrences + finding.occurrences}
        )
    return tuple(by_fingerprint[key] for key in sorted(by_fingerprint))
