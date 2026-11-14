"""Construtor comum dos achados de autorização: fingerprint, CWE, OWASP e identificador.

Todo construtor de achado (um por técnica, em `authz_findings` e nos módulos das técnicas
seguintes) termina em `build_finding`: é aqui que o `finding_id`, o fingerprint e a classe
(CWE e categoria do OWASP API Top 10 2023) saem da técnica, para que nenhum construtor
decida isso por conta própria. O fingerprint não inclui as contas nem os códigos HTTP. Este
módulo é puro e não escolhe severidade nem texto: recebe tudo pronto.
"""

import hashlib
from typing import Final

from harness_dast.domain.authz_fields import CandidateSource
from harness_dast.domain.authz_result import (
    AUTHZ_FINGERPRINT_VERSION,
    AuthzFinding,
    AuthzTechnique,
)
from harness_dast.domain.authz_token import TamperVariant
from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.zap_alert import Severity

TECHNIQUE_CLASS: Final[dict[AuthzTechnique, tuple[int, str]]] = {
    "authz_horizontal": (639, "API1:2023 Broken Object Level Authorization"),
    "authz_vertical": (285, "API5:2023 Broken Function Level Authorization"),
    "authz_excessive_data": (213, "API3:2023 Broken Object Property Level Authorization"),
    "authz_mass_assignment": (915, "API3:2023 Broken Object Property Level Authorization"),
    "authz_anonymous_access": (306, "API2:2023 Broken Authentication"),
    "authz_tampered_token": (347, "API2:2023 Broken Authentication"),
}
"""CWE e categoria do OWASP API Top 10 2023 de cada técnica (sem inferência)."""


def authz_fingerprint(
    *,
    product: str,
    technique: AuthzTechnique,
    method: str,
    path_template: str,
    fields: tuple[str, ...],
) -> str:
    """SHA-256 (hex) do achado: técnica, produto, método, modelo de caminho e campos."""
    parts = (
        f"hdast-authz-v{AUTHZ_FINGERPRINT_VERSION}",
        product,
        technique,
        method.upper(),
        normalize_path_template(path_template),
        ",".join(sorted(fields)),
    )
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_finding(
    *,
    product: str,
    technique: AuthzTechnique,
    title: str,
    severity: Severity,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    owner: tuple[str, str | None] | None,
    statuses: tuple[int | None, int | None],
    fields: tuple[str, ...],
    evidence: str,
    description: str,
    solution: str,
    variants: tuple[TamperVariant, ...] = (),
    cwe: int | None = None,
    candidate_source: CandidateSource | None = None,
) -> AuthzFinding:
    """Monta o achado com fingerprint, `finding_id` e classe derivados da técnica.

    `candidate_source` (só da atribuição em massa) também fica fora do fingerprint.
    `variants` não entra no fingerprint (o mesmo problema segue o mesmo achado entre execuções).
    `cwe` só substitui o CWE padrão da técnica quando o domínio decide outro (token adulterado).
    """
    fingerprint = authz_fingerprint(
        product=product,
        technique=technique,
        method=method,
        path_template=path_template,
        fields=fields,
    )
    default_cwe, category = TECHNIQUE_CLASS[technique]
    return AuthzFinding(
        finding_id=f"A-{fingerprint[:8]}",
        fingerprint=fingerprint,
        technique=technique,
        title=title,
        proposed_severity=severity,
        cwe=cwe if cwe is not None else default_cwe,
        owasp_api_2023=category,
        operation_id=operation_id,
        method=method.upper(),
        path_template=normalize_path_template(path_template),
        actor_account=actor[0],
        actor_role=actor[1],
        owner_account=owner[0] if owner else None,
        owner_role=owner[1] if owner else None,
        baseline_status=statuses[0],
        observed_status=statuses[1],
        fields=fields,
        variants=variants,
        candidate_source=candidate_source,
        evidence=evidence,
        description=description,
        solution=solution,
    )
