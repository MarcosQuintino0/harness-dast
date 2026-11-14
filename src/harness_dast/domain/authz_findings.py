"""Construtores dos achados de autorização por técnica: severidade, rótulo e texto.

A severidade é decidida AQUI, em código, a partir da técnica e do NOME dos campos; nem o
agente nem o adaptador a escolhem:

| técnica                  | severidade                                              |
| ------------------------ | ------------------------------------------------------- |
| authz_horizontal         | alta                                                    |
| authz_vertical           | alta                                                    |
| authz_mass_assignment    | alta                                                    |
| authz_excessive_data     | média; alta se algum campo tem nome de segredo/pessoal  |

O CWE, a categoria do OWASP API Top 10 2023 e o fingerprint saem de `build_finding`
(`authz_finding_build`): são os da própria técnica, sem inferência. O fingerprint não inclui
as contas nem os códigos HTTP: o mesmo problema é o mesmo achado entre execuções. Este módulo
é puro.
"""

from typing import Final

from harness_dast.domain.authz_finding_build import build_finding
from harness_dast.domain.authz_result import AuthzFinding, AuthzTechnique
from harness_dast.domain.authz_sensitive import classify_field_name
from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.zap_alert import Severity

TECHNIQUE_LABEL: Final[dict[AuthzTechnique, str]] = {
    "authz_horizontal": "Acesso horizontal entre contas do mesmo papel (BOLA/IDOR)",
    "authz_vertical": "Acesso vertical: papel menor chama operação de papel maior (BFLA)",
    "authz_excessive_data": "Exposição excessiva de dados (campos fora do esquema)",
    "authz_mass_assignment": "Atribuição em massa (campo extra aceito)",
    "authz_anonymous_access": "Acesso sem login",
    "authz_tampered_token": "Token adulterado aceito",
}
"""Nome legível de cada técnica, usado no relatório."""

_MAX_NAMES_IN_TITLE: Final = 3


def severity_for_fields(paths: tuple[str, ...]) -> Severity:
    """Severidade da exposição excessiva: média, ou alta se algum campo tem nome sensível."""
    for path in paths:
        name = path.rsplit(".", 1)[-1].removesuffix("[]")
        if classify_field_name(name) in {"secret", "personal"}:
            return "high"
    return "medium"


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
    return build_finding(
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
    return build_finding(
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
    return build_finding(
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
    return build_finding(
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
