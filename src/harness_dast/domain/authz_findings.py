"""Taxonomia e construção dos achados de autorização: severidade, CWE, OWASP e fingerprint.

A severidade é decidida AQUI, em código, a partir da técnica e do NOME dos campos; nem o
agente nem o adaptador a escolhem:

| técnica                  | severidade                                              |
| ------------------------ | ------------------------------------------------------- |
| authz_horizontal         | alta                                                    |
| authz_vertical           | alta                                                    |
| authz_mass_assignment    | alta                                                    |
| authz_excessive_data     | média; alta se algum campo tem nome de segredo/pessoal  |

Para as técnicas próprias o CWE e a categoria do OWASP API Top 10 2023 são os da própria
técnica (não há inferência a partir de um CWE ambíguo). O fingerprint não inclui as contas
nem os códigos HTTP: o mesmo problema é o mesmo achado entre execuções. Este módulo é puro.
"""

import hashlib
from typing import Final

from harness_dast.domain.authz_result import (
    AUTHZ_FINGERPRINT_VERSION,
    AuthzFinding,
    AuthzTechnique,
)
from harness_dast.domain.authz_sensitive import classify_field_name
from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.zap_alert import Severity

TECHNIQUE_LABEL: Final[dict[AuthzTechnique, str]] = {
    "authz_horizontal": "Acesso horizontal entre contas do mesmo papel (BOLA/IDOR)",
    "authz_vertical": "Acesso vertical: papel menor chama operação de papel maior (BFLA)",
    "authz_excessive_data": "Exposição excessiva de dados (campos fora do esquema)",
    "authz_mass_assignment": "Atribuição em massa (campo extra aceito)",
}
"""Nome legível de cada técnica, usado no relatório."""

_CLASS: Final[dict[AuthzTechnique, tuple[int, str]]] = {
    "authz_horizontal": (639, "API1:2023 Broken Object Level Authorization"),
    "authz_vertical": (285, "API5:2023 Broken Function Level Authorization"),
    "authz_excessive_data": (213, "API3:2023 Broken Object Property Level Authorization"),
    "authz_mass_assignment": (915, "API3:2023 Broken Object Property Level Authorization"),
}
_MAX_NAMES_IN_TITLE: Final = 3


def severity_for_fields(paths: tuple[str, ...]) -> Severity:
    """Severidade da exposição excessiva: média, ou alta se algum campo tem nome sensível."""
    for path in paths:
        name = path.rsplit(".", 1)[-1].removesuffix("[]")
        if classify_field_name(name) in {"secret", "personal"}:
            return "high"
    return "medium"


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


def _build(
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
) -> AuthzFinding:
    fingerprint = authz_fingerprint(
        product=product,
        technique=technique,
        method=method,
        path_template=path_template,
        fields=fields,
    )
    cwe, category = _CLASS[technique]
    return AuthzFinding(
        finding_id=f"A-{fingerprint[:8]}",
        fingerprint=fingerprint,
        technique=technique,
        title=title,
        proposed_severity=severity,
        cwe=cwe,
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
        evidence=evidence,
        description=description,
        solution=solution,
    )


def horizontal_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    owner: tuple[str, str | None],
    statuses: tuple[int, int],
) -> AuthzFinding:
    """Achado de BOLA: outra conta do mesmo papel leu o recurso com o mesmo conteúdo."""
    return _build(
        product=product,
        technique="authz_horizontal",
        title=f"{method.upper()} {normalize_path_template(path_template)} devolve o recurso "
        "de uma conta a outra do mesmo papel",
        severity="high",
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=owner,
        statuses=statuses,
        fields=(),
        evidence=(
            f"A conta {owner[0]} e a conta {actor[0]} (mesmo papel) receberam resposta "
            f"{statuses[0]} e {statuses[1]} com corpo equivalente para o mesmo pedido."
        ),
        description=(
            "Um usuário consegue ler um recurso que pertence a outro usuário do mesmo papel, "
            "só trocando o identificador (BOLA/IDOR)."
        ),
        solution=(
            "Conferir, no servidor, que o recurso pertence a quem chama (ou que o papel "
            "permite) antes de devolvê-lo; responder 403 ou 404 caso contrário."
        ),
    )


def vertical_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    owner: tuple[str, str | None],
    statuses: tuple[int, int],
) -> AuthzFinding:
    """Achado de BFLA: conta de papel menor executou operação atribuída a papel maior."""
    return _build(
        product=product,
        technique="authz_vertical",
        title=f"{method.upper()} {normalize_path_template(path_template)} aceita conta de "
        "papel menor",
        severity="high",
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=owner,
        statuses=statuses,
        fields=(),
        evidence=(
            f"A operação é atribuída à conta {owner[0]} (papel {owner[1]}) e a conta "
            f"{actor[0]} (papel {actor[1]}, menor) recebeu {statuses[1]} ao repetir o pedido."
        ),
        description=(
            "Uma conta de papel menor consegue executar uma função reservada a um papel maior "
            "(BFLA)."
        ),
        solution="Exigir o papel necessário na própria operação; responder 403 aos demais.",
    )


def excessive_data_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    status: int,
    fields: tuple[str, ...],
) -> AuthzFinding:
    """Achado de exposição excessiva: a resposta traz campos que o esquema não declara."""
    shown = ", ".join(fields[:_MAX_NAMES_IN_TITLE])
    more = len(fields) - _MAX_NAMES_IN_TITLE
    suffix = f" e mais {more}" if more > 0 else ""
    return _build(
        product=product,
        technique="authz_excessive_data",
        title=f"{method.upper()} {normalize_path_template(path_template)} devolve campos fora "
        f"do esquema ({shown}{suffix})",
        severity=severity_for_fields(fields),
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=None,
        statuses=(None, status),
        fields=fields,
        evidence=(
            f"A resposta {status} traz {len(fields)} campo(s) que o OpenAPI não declara. "
            "Só os nomes foram gravados; os valores não."
        ),
        description=(
            "A API devolve mais dados do que o contrato declara. Campos internos, hashes ou "
            "dados pessoais expostos por engano ampliam o impacto de qualquer vazamento."
        ),
        solution=(
            "Devolver só os campos do contrato (use um objeto de resposta próprio, não a "
            "entidade) e conferir o esquema do OpenAPI."
        ),
    )


def mass_assignment_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    sent_field: str,
    changed: tuple[str, ...],
    status: int,
    restored: bool | None,
) -> AuthzFinding:
    """Achado de atribuição em massa: o campo extra enviado mudou o estado do recurso."""
    state = {
        True: "O valor anterior foi restaurado e conferido.",
        False: "Não foi possível restaurar o valor anterior: confira o estado da conta.",
        None: "Não havia valor anterior para restaurar.",
    }[restored]
    return _build(
        product=product,
        technique="authz_mass_assignment",
        title=f"{method.upper()} {normalize_path_template(path_template)} aceita o campo "
        f"extra '{sent_field}'",
        severity="high",
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=None,
        statuses=(None, status),
        fields=(sent_field, *changed),
        evidence=(
            f"Ao enviar o campo '{sent_field}' junto do corpo válido, a leitura seguinte "
            f"mostrou o valor injetado em: {', '.join(changed)}. {state}"
        ),
        description=(
            "A API copia campos do corpo para o objeto sem lista de campos permitidos; um "
            "usuário comum pode alterar atributos que não deveria (por exemplo, o papel)."
        ),
        solution=(
            "Usar um objeto de entrada com só os campos editáveis e ignorar ou recusar os "
            "demais; nunca ligar o corpo diretamente à entidade."
        ),
    )
