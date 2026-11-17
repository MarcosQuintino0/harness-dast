"""Achado de escrita em recurso de outra conta (`authz_horizontal_write`, ADR 0042).

Severidade alta (CWE 639, OWASP API1:2023): o efeito foi PROVADO (a conta dona leu o marcador no
campo depois da escrita da outra conta). O título e a evidência dizem o NOME do campo, nunca o
valor. `fields` leva `(campo,)`. Este módulo é puro.
"""

from harness_dast.domain.authz.finding_build import build_finding
from harness_dast.domain.authz.result import AuthzFinding
from harness_dast.domain.finding import normalize_path_template


def horizontal_write_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    owner: tuple[str, str | None],
    status: int,
    field: str,
    restored: bool,
) -> AuthzFinding:
    """A conta `actor` alterou o campo `field` do recurso da conta `owner`.

    Args:
        product: Produto.
        operation_id: Operação (`PUT` ou `PATCH`) repetida.
        method: Método HTTP.
        path_template: Modelo de caminho.
        actor: Apelido e papel da conta que escreveu.
        owner: Apelido e papel da conta dona do recurso.
        status: Código HTTP da escrita da conta `actor`.
        field: Nome do campo do marcador (nunca o valor).
        restored: Se a conta dona devolveu o valor anterior e a conferência confirmou.
    """
    template = normalize_path_template(path_template)
    state = (
        "O valor anterior foi restaurado e a restauração foi conferida."
        if restored
        else "O valor anterior NÃO pôde ser restaurado com certeza: confira o recurso e "
        "restaure por fora (reset do ambiente ou `cleanup`)."
    )
    return build_finding(
        product=product,
        technique="authz_horizontal_write",
        title=f"{method.upper()} {template} deixa uma conta alterar o recurso de outra conta "
        "do mesmo papel",
        severity="high",
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=owner,
        statuses=(None, status),
        fields=(field,),
        evidence=(
            f"A conta {actor[0]} alterou o campo `{field}` do recurso da conta {owner[0]} "
            f"(mesmo papel): a escrita recebeu {status} e a conta {owner[0]} leu o valor "
            f"de teste no campo depois. {state}"
        ),
        description=(
            "Um usuário consegue ALTERAR um recurso que pertence a outro usuário do mesmo "
            "papel, só repetindo o pedido de escrita com o identificador dele (BOLA/IDOR)."
        ),
        solution=(
            "Conferir, no servidor, que o recurso pertence a quem chama antes de gravar; "
            "responder 403 ou 404 caso contrário."
        ),
    )
