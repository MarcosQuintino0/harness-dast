"""Construção do achado do teste negativo: fingerprint, classe CWE e texto (ADR 0051).

A severidade vem de `negative_verdict.proposed_severity`; o fingerprint não inclui o código HTTP,
o valor enviado nem a execução (o mesmo problema é o mesmo achado entre execuções). Nenhum texto
repete o valor enviado nem valor do alvo: só nomes, limites declarados no contrato e códigos.
Este módulo é puro.
"""

import hashlib
from typing import Final

from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.negative_plan import NegativeCase
from harness_dast.domain.negative_result import (
    NEGATIVE_FINGERPRINT_VERSION,
    NegativeFinding,
    NegativeTechnique,
)
from harness_dast.domain.negative_values import CaseClass
from harness_dast.domain.negative_verdict import Verdict, proposed_severity

TECHNIQUE_CLASS: Final[dict[NegativeTechnique, tuple[int, str]]] = {
    "input_accepted": (20, "API8:2023 Security Misconfiguration"),
    "input_server_error": (755, "API8:2023 Security Misconfiguration"),
}
"""CWE e categoria proposta do OWASP API Top 10 2023 de cada técnica."""

_CLASS_TEXT: Final[dict[CaseClass, str]] = {
    "wrong_type": "de tipo diferente do declarado",
    "missing_required": "sem um campo obrigatório",
    "below_minimum": "abaixo do mínimo declarado",
    "above_maximum": "acima do máximo declarado",
    "not_in_enum": "fora da lista de valores declarada",
    "too_long": "maior que o tamanho máximo declarado",
    "too_short": "menor que o tamanho mínimo declarado",
}
_CLASS_LABEL: Final[dict[CaseClass, str]] = {
    "wrong_type": "tipo errado",
    "missing_required": "campo obrigatório ausente",
    "below_minimum": "abaixo do mínimo",
    "above_maximum": "acima do máximo",
    "not_in_enum": "fora do enum",
    "too_long": "texto longo demais",
    "too_short": "texto curto demais",
}
_LABEL: Final[dict[NegativeTechnique, str]] = {
    "input_accepted": "Valor que o contrato proíbe foi aceito",
    "input_server_error": "Valor que o contrato proíbe causou erro do servidor",
}


def negative_fingerprint(*, product: str, technique: NegativeTechnique, case: NegativeCase) -> str:
    """SHA-256 (hex): produto, técnica, método, modelo de caminho, local, campo e classe."""
    parts = (
        f"hdast-negative-v{NEGATIVE_FINGERPRINT_VERSION}",
        product,
        technique,
        case.exchange.method.upper(),
        normalize_path_template(case.exchange.path),
        case.location,
        case.field,
        case.case_class,
    )
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_negative_finding(
    *,
    product: str,
    technique: NegativeTechnique,
    case: NegativeCase,
    status: int,
    restored: bool | None,
    created: bool,
) -> NegativeFinding:
    """Monta o achado de um caso aceito ou que causou 5xx.

    Args:
        product: Produto.
        technique: `input_accepted` ou `input_server_error`.
        case: O caso enviado (o valor dele nunca vai para o achado).
        status: Código HTTP da reação.
        restored: Resultado da restauração (PUT e PATCH), ou `None` se não se aplica.
        created: Se um POST pode ter criado um recurso.
    """
    exchange = case.exchange
    method = exchange.method.upper()
    where = "na consulta" if case.location == "query" else "no corpo"
    verdict: Verdict = "accepted" if technique == "input_accepted" else "server_error"
    cwe, category = TECHNIQUE_CLASS[technique]
    fingerprint = negative_fingerprint(product=product, technique=technique, case=case)
    path = normalize_path_template(exchange.path)
    if technique == "input_accepted":
        what = f"aceitou com {status} um pedido {_CLASS_TEXT[case.case_class]}"
        description = (
            "O servidor aceitou um valor que o contrato (OpenAPI) proíbe: o dado inválido entra "
            "no sistema e pode quebrar regras de negócio mais adiante. Pode ser coerção "
            "legítima ou parâmetro ignorado: confirme na triagem."
        )
        solution = (
            "Validar a entrada contra o contrato no servidor e responder 4xx a valor proibido."
        )
    else:
        what = f"respondeu {status} a um pedido {_CLASS_TEXT[case.case_class]}"
        description = (
            "O servidor falhou (5xx) diante de um valor que o contrato (OpenAPI) proíbe: há uma "
            "exceção sem tratamento. Em escrita, o estado do recurso pode ter ficado inconsistente."
        )
        solution = "Tratar o valor inválido e responder 4xx em vez de falhar."
    return NegativeFinding(
        finding_id=f"N-{fingerprint[:8]}",
        fingerprint=fingerprint,
        technique=technique,
        title=f"{method} {path}: {_LABEL[technique].lower()} ({_CLASS_LABEL[case.case_class]})",
        proposed_severity=proposed_severity(method, case.case_class, verdict),
        cwe=cwe,
        owasp_api_2023=category,
        operation_id=exchange.operation_id,
        method=method,
        path_template=path,
        account=exchange.account,
        location=case.location,
        field=case.field,
        case_class=case.case_class,
        declared=case.declared,
        observed_status=status,
        baseline_status=exchange.status,
        restored=restored,
        created=created,
        evidence=(
            f"Com um valor válido, o probe recebeu {exchange.status}; o campo '{case.field}' "
            f"{where} foi alterado (um campo por pedido; contrato: {case.declared}) e o "
            f"servidor {what}."
        ),
        description=description,
        solution=solution,
    )
