"""Transforma alertas brutos do ZAP em achados: resolve a operação, deduplica e escolhe a evidência.

Resolução da operação de origem, em ordem (o URL do alerta é o URL ATACADO e nunca serve de
identidade):

1. `sourceMessageId` está entre as mensagens aprendidas do `probe`: `source_message`;
2. o alerta foi gerado durante a varredura de uma operação (delta de alertas): `scan`;
3. o caminho do alerta casa com UM modelo de caminho do `probe`: `url_match`;
4. nenhuma das anteriores: `unresolved`, com modelo aproximado do caminho.

Alertas iguais pelo fingerprint viram um achado com a contagem de ocorrências. Nada é
descartado: confiança `false_positive` do ZAP continua sendo achado. Este módulo é puro.
"""

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.curl_repro import build_curl
from harness_dast.domain.finding import (
    Attribution,
    Classification,
    Finding,
    FindingEvidence,
    compute_fingerprint,
    generic_template,
    normalize_path_template,
)
from harness_dast.domain.finding_taxonomy import owasp_api_category
from harness_dast.domain.redaction import EvidenceMessage, strip_control
from harness_dast.domain.zap_alert import (
    SEVERITY_RANK,
    RawAlert,
    confidence_rank,
    int_or_none,
    parse_confidence,
    parse_severity,
)

_TAGS: Final = re.compile(r"<[^>]*>")
_TEXT_CAP: Final = 1500
_TITLE_CAP: Final = 200


class OperationRef(ApiModel):
    """Operação do `probe`.

    Attributes:
        operation_id: Identificador.
        method: Método HTTP.
        path: Modelo de caminho do OpenAPI.
    """

    operation_id: str
    method: str
    path: str


@dataclass(frozen=True)
class Resolution:
    """Operação a que um alerta pertence e como isso foi decidido."""

    operation: OperationRef | None
    method: str
    path_template: str
    attribution: Attribution


@dataclass(frozen=True)
class AlertResolver:
    """Ligações entre alertas e operações do `probe`."""

    by_message: Mapping[int, OperationRef]
    by_alert: Mapping[str, OperationRef]
    operations: Sequence[OperationRef]

    def resolve(self, alert: RawAlert) -> Resolution:
        """Resolve o alerta pela ordem documentada no módulo."""
        source = int_or_none(alert.source_message_id)
        if source is not None and source in self.by_message:
            return self._found(self.by_message[source], "source_message")
        if alert.id in self.by_alert:
            return self._found(self.by_alert[alert.id], "scan")
        matched = self._match_url(alert)
        if matched is not None:
            return self._found(matched, "url_match")
        path = urlsplit(alert.url).path
        return Resolution(None, alert.method.upper(), generic_template(path), "unresolved")

    @staticmethod
    def _found(operation: OperationRef, attribution: Attribution) -> Resolution:
        template = normalize_path_template(operation.path)
        return Resolution(operation, operation.method.upper(), template, attribution)

    def resolve_path(self, method: str, path: str) -> OperationRef | None:
        """Operação do `probe` cujo modelo casa, sem ambiguidade, com `method` e o caminho."""
        hits = [
            (op, _literal_segments(op.path))
            for op in self.operations
            if op.method.upper() == method.upper() and _template_matches(op.path, path)
        ]
        if not hits:
            return None
        best = max(score for _, score in hits)
        top = [op for op, score in hits if score == best]
        return top[0] if len(top) == 1 else None

    def _match_url(self, alert: RawAlert) -> OperationRef | None:
        return self.resolve_path(alert.method, urlsplit(alert.url).path)


def _literal_segments(template: str) -> int:
    return sum(1 for item in normalize_path_template(template).split("/") if item and item != "{}")


def _template_matches(template: str, path: str) -> bool:
    pattern = "/".join(
        "[^/]+" if item == "{}" else re.escape(item)
        for item in normalize_path_template(template).split("/")
    )
    return re.fullmatch(pattern, "/" + path.strip("/")) is not None


def plain_text(value: str, cap: int = _TEXT_CAP) -> str:
    """Texto simples de um campo com HTML do ZAP: sem tags, sem controle, cortado em `cap`."""
    text = html.unescape(_TAGS.sub(" ", value))
    text = " ".join(strip_control(text, keep_newlines=False).split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _sort_key(alert: RawAlert) -> tuple[int, int, int]:
    return (
        -SEVERITY_RANK[parse_severity(alert.risk)],
        -confidence_rank(parse_confidence(alert.confidence)),
        int_or_none(alert.id) or 0,
    )


def _evidence_for(
    ordered: Sequence[RawAlert], evidence: Mapping[int, EvidenceMessage]
) -> FindingEvidence:
    best = ordered[0]
    for alert in ordered:
        message_id = int_or_none(alert.message_id)
        message = evidence.get(message_id) if message_id is not None else None
        if message is not None:
            return FindingEvidence(
                message_id=message.message_id,
                attack=alert.attack,
                zap_evidence=alert.evidence,
                request_header=message.request_header,
                request_body=message.request_body,
                response_header=message.response_header,
                response_body=message.response_body,
                truncated=message.truncated,
            )
    return FindingEvidence(
        message_id=int_or_none(best.message_id),
        attack=best.attack,
        zap_evidence=best.evidence,
        available=False,
    )


def _finding(
    group: Sequence[tuple[RawAlert, Resolution]],
    *,
    fingerprint: str,
    evidence: Mapping[int, EvidenceMessage],
    auth_header: tuple[str, str] | None,
    csrf_header: str | None,
) -> Finding:
    ordered = sorted((item[0] for item in group), key=_sort_key)
    best = ordered[0]
    resolution = next(res for alert, res in group if alert is best)
    cwe = int_or_none(best.cwe_id)
    proof = _evidence_for(ordered, evidence)
    return Finding(
        finding_id=f"F-{fingerprint[:8]}",
        fingerprint=fingerprint,
        title=plain_text(best.name, _TITLE_CAP) or f"Alerta {best.plugin_id}",
        plugin_id=best.plugin_id,
        alert_ref=best.alert_ref,
        classification=Classification(
            cwe=cwe, wasc=int_or_none(best.wasc_id), owasp_api_2023=owasp_api_category(cwe)
        ),
        proposed_severity=parse_severity(best.risk),
        proposed_confidence=parse_confidence(best.confidence),
        operation_id=resolution.operation.operation_id if resolution.operation else None,
        method=resolution.method,
        path_template=resolution.path_template,
        attribution=resolution.attribution,
        input_vector=best.input_vector.strip().lower(),
        parameter=plain_text(best.param, 120),
        occurrences=len(group),
        evidence=proof,
        description=plain_text(best.description),
        solution=plain_text(best.solution),
        reproduce_curl=build_curl(proof, auth_header=auth_header, csrf_header=csrf_header),
    )


def _fingerprint_of(alert: RawAlert, resolution: Resolution, product: str) -> str:
    return compute_fingerprint(
        product=product,
        method=resolution.method,
        path_template=resolution.path_template,
        input_vector=alert.input_vector,
        parameter=alert.param,
        plugin_id=alert.plugin_id,
        alert_ref=alert.alert_ref,
        cwe=int_or_none(alert.cwe_id),
    )


def build_findings(
    alerts: Sequence[RawAlert],
    *,
    product: str,
    resolver: AlertResolver,
    evidence: Mapping[int, EvidenceMessage],
    auth_header: tuple[str, str] | None = None,
    csrf_header: str | None = None,
) -> tuple[Finding, ...]:
    """Agrupa os alertas por fingerprint e produz um achado por grupo, em ordem estável.

    A ordem é severidade proposta (maior primeiro), confiança, título e fingerprint.
    """
    groups: dict[str, list[tuple[RawAlert, Resolution]]] = {}
    for alert in alerts:
        resolution = resolver.resolve(alert)
        groups.setdefault(_fingerprint_of(alert, resolution, product), []).append(
            (alert, resolution)
        )
    findings = [
        _finding(
            group,
            fingerprint=fingerprint,
            evidence=evidence,
            auth_header=auth_header,
            csrf_header=csrf_header,
        )
        for fingerprint, group in groups.items()
    ]
    findings.sort(
        key=lambda f: (
            -SEVERITY_RANK[f.proposed_severity],
            -confidence_rank(f.proposed_confidence),
            f.title,
            f.fingerprint,
        )
    )
    return tuple(findings)
