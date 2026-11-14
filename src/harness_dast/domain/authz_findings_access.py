"""Construtores dos achados "acesso sem login" e "token adulterado aceito" (ADR 0039).

A severidade e o CWE são decididos em código (`authz_anonymous`), nunca pelo agente:

| técnica                 | severidade                                              | CWE          |
| ----------------------- | ------------------------------------------------------- | ------------ |
| authz_anonymous_access  | alta se o OpenAPI exige autenticação; média se não      | 306          |
|                         | declara `security`                                      |              |
| authz_tampered_token    | alta                                                    | 347 ou 287   |

Nenhum valor de token entra no texto: só o nome das variantes aceitas. Este módulo é puro.
"""

from collections.abc import Sequence

from harness_dast.domain.api_model import Operation
from harness_dast.domain.authz_anonymous import anonymous_severity, tampered_cwe
from harness_dast.domain.authz_finding_build import build_finding
from harness_dast.domain.authz_result import AuthzFinding
from harness_dast.domain.authz_token import TamperVariant
from harness_dast.domain.finding import normalize_path_template

VARIANT_LABEL: dict[TamperVariant, str] = {
    "stripped_signature": "sem a assinatura",
    "alg_none": "com algoritmo none",
    "altered_claims": "com uma reivindicação a mais",
    "scrambled": "com o texto embaralhado",
}
"""Descrição curta de cada variante, usada na evidência."""


def anonymous_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    operation: Operation | None,
    statuses: tuple[int, int],
) -> AuthzFinding:
    """Achado de acesso sem login: o mesmo pedido, sem credencial, devolveu o mesmo conteúdo."""
    severity = anonymous_severity(operation)
    declared = severity == "high"
    basis = (
        "O OpenAPI declara que a operação exige autenticação."
        if declared
        else "O OpenAPI não declara `security` nesta operação: se ela deve ser pública, "
        "registre-a em authz.public_operations."
    )
    return build_finding(
        product=product,
        technique="authz_anonymous_access",
        title=f"{method.upper()} {normalize_path_template(path_template)} responde a quem não "
        "fez login",
        severity=severity,
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=None,
        statuses=statuses,
        fields=(),
        evidence=(
            f"A conta {actor[0]} recebeu {statuses[0]} com o pedido autenticado e "
            f"{statuses[1]} com corpo equivalente ao enviar o mesmo pedido sem credencial. "
            f"{basis}"
        ),
        description=(
            "A operação devolve o mesmo conteúdo a quem não se identificou: falta exigir "
            "autenticação (ou ela não está sendo conferida)."
        ),
        solution=(
            "Exigir autenticação na operação e responder 401 a quem não enviou credencial "
            "válida; se ela deve ser pública, declare isso no OpenAPI e no perfil."
        ),
    )


def tampered_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    variants: Sequence[TamperVariant],
    statuses: tuple[int, int],
) -> AuthzFinding:
    """Achado de token adulterado aceito: o servidor não conferiu o token que recebeu."""
    accepted = tuple(variants)
    names = ", ".join(VARIANT_LABEL[name] for name in accepted)
    return build_finding(
        product=product,
        technique="authz_tampered_token",
        title=f"{method.upper()} {normalize_path_template(path_template)} aceita um token "
        "adulterado",
        severity="high",
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=None,
        statuses=statuses,
        fields=(),
        variants=accepted,
        cwe=tampered_cwe(accepted),
        evidence=(
            f"O token da conta {actor[0]}, enviado {names}, recebeu {statuses[1]} com corpo "
            "equivalente ao do pedido autenticado. O valor do token não foi gravado."
        ),
        description=(
            "O servidor aceitou um token que não pode ser válido: a assinatura (ou o próprio "
            "token) não é conferida. Qualquer pessoa poderia fabricar uma credencial."
        ),
        solution=(
            "Validar a assinatura e o algoritmo de todo token em toda requisição, recusar "
            "`alg: none` e responder 401 a token inválido."
        ),
    )
