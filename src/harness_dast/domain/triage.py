"""Triagem do agente: anotações em arquivo SEPARADO que o `report` mescla como coluna extra.

Contrato de `runs/<run_id>/triage.json`:

```json
{"schema_version": 1,
 "annotations": [
   {"fingerprint": "<64 hex>", "note": "texto", "suspected_false_positive": true,
    "reason": "por que"}]}
```

A triagem é consultiva. O modelo NÃO tem campo de severidade, status nem de remoção, e rejeita
campos desconhecidos: tentar `{"severity": "low"}` ou `{"delete": true}` é erro de validação.
`merge_triage` devolve os mesmos achados, na mesma ordem e com os mesmos valores, só com o campo
`triage` preenchido. Anotação cujo fingerprint não existe é devolvida como órfã e ignorada. Todo
texto da anotação é do agente (não confiável para o relatório). Este módulo é puro.
"""

import re
from collections.abc import Sequence
from typing import Final, Literal, Self

from pydantic import ValidationError, field_validator, model_validator

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.finding import Finding, TriageNote
from harness_dast.domain.redaction import strip_control

_FINGERPRINT: Final = re.compile(r"[0-9a-f]{64}")
_HINT: Final = (
    "Cada anotação aceita só fingerprint, note, suspected_false_positive e reason. "
    "A triagem nunca muda severidade nem remove achados."
)
NOTE_CAP: Final = 500
MAX_ANNOTATIONS: Final = 5000


class TriageEntry(ApiModel):
    """Uma anotação.

    Attributes:
        fingerprint: Fingerprint (64 hexadecimais) do achado anotado.
        note: Observação livre.
        suspected_false_positive: Se o agente suspeita de falso positivo.
        reason: Motivo da suspeita; obrigatório quando há suspeita.
    """

    fingerprint: str
    note: str = ""
    suspected_false_positive: bool = False
    reason: str = ""

    @field_validator("fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        """Exige 64 hexadecimais minúsculos."""
        if not _FINGERPRINT.fullmatch(value):
            raise ValueError("fingerprint deve ter 64 hexadecimais minúsculos")
        return value

    @field_validator("note", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Limita o tamanho dos textos."""
        if len(value) > NOTE_CAP:
            raise ValueError(f"texto acima de {NOTE_CAP} caracteres")
        return value

    @model_validator(mode="after")
    def validate_reason(self) -> Self:
        """Suspeita de falso positivo exige motivo."""
        if self.suspected_false_positive and not self.reason.strip():
            raise ValueError("suspected_false_positive exige reason")
        return self


class TriageFile(ApiModel):
    """`triage.json`.

    Attributes:
        schema_version: Versão do formato (1).
        annotations: Anotações, no máximo uma por fingerprint.
    """

    schema_version: Literal[1]
    annotations: tuple[TriageEntry, ...]

    @field_validator("annotations")
    @classmethod
    def validate_unique(cls, value: tuple[TriageEntry, ...]) -> tuple[TriageEntry, ...]:
        """Recusa fingerprint repetido e excesso de anotações."""
        if len(value) > MAX_ANNOTATIONS:
            raise ValueError("anotações demais")
        if len({item.fingerprint for item in value}) != len(value):
            raise ValueError("mais de uma anotação para o mesmo fingerprint")
        return value


def _describe(error_type: str, ctx_error: str | None) -> str:
    if error_type == "extra_forbidden":
        return "campo não permitido (a triagem não altera severidade nem status)"
    if error_type == "missing":
        return "campo obrigatório ausente"
    if error_type == "value_error" and ctx_error:
        return ctx_error
    return "valor inválido"


def parse_triage(data: object) -> TriageFile:
    """Valida o conteúdo de `triage.json`.

    Raises:
        ConfigError: Estrutura inválida. A mensagem lista o caminho e um texto fixo de cada
            problema, nunca o valor recebido.
    """
    try:
        return TriageFile.model_validate(data)
    except ValidationError as error:
        lines = sorted(
            {
                "- "
                + (".".join(str(part) for part in item["loc"]) or "(arquivo)")
                + ": "
                + _describe(item["type"], str(item.get("ctx", {}).get("error", "")) or None)
                for item in error.errors()
            }
        )
        raise ConfigError(
            f"triage.json inválido ({len(lines)} problema(s)):\n" + "\n".join(lines), hint=_HINT
        ) from None


def merge_triage(
    findings: Sequence[Finding], triage: TriageFile
) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
    """Anexa a triagem aos achados sem remover nem alterar nada além de `triage`.

    Returns:
        Os achados (mesma ordem e mesmo tamanho) e os fingerprints órfãos da triagem.
    """
    notes = {item.fingerprint: item for item in triage.annotations}
    merged: list[Finding] = []
    for finding in findings:
        entry = notes.get(finding.fingerprint)
        if entry is None:
            merged.append(finding)
            continue
        note = TriageNote(
            note=strip_control(entry.note, keep_newlines=False),
            suspected_false_positive=entry.suspected_false_positive,
            reason=strip_control(entry.reason, keep_newlines=False),
        )
        merged.append(finding.model_copy(update={"triage": note}))
    known = {finding.fingerprint for finding in findings}
    return tuple(merged), tuple(sorted(set(notes) - known))
