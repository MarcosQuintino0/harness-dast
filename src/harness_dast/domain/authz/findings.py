"""Construtores dos achados de autorização por técnica: severidade, rótulo e texto.

A severidade é decidida AQUI, em código, a partir da técnica e do NOME dos campos; nem o
agente nem o adaptador a escolhem:

| técnica                  | severidade                                              |
| ------------------------ | ------------------------------------------------------- |
| authz_horizontal         | alta; média se só o NOME indica identificador de consulta |
| authz_horizontal_write   | alta                                                    |
| authz_vertical           | alta                                                    |
| authz_access_matrix      | alta                                                    |
| authz_mass_assignment    | alta (declarado, privilégio, saldo); média (preço, estado, outros) |
| authz_excessive_data     | média; alta se algum campo tem nome de segredo/pessoal  |

O CWE, a categoria do OWASP API Top 10 2023 e o fingerprint saem de `build_finding`
(`authz_finding_build`): são os da própria técnica, sem inferência. O fingerprint não inclui
as contas nem os códigos HTTP: o mesmo problema é o mesmo achado entre execuções. Este módulo
é puro.
"""

from typing import Final, Literal

from harness_dast.domain.authz.candidates import mass_severity
from harness_dast.domain.authz.fields import CandidateKind, CandidateSource
from harness_dast.domain.authz.finding_build import build_finding
from harness_dast.domain.authz.identifiers import IdentifierRef
from harness_dast.domain.authz.result import AuthzFinding, AuthzTechnique
from harness_dast.domain.authz.sensitive import classify_field_name
from harness_dast.domain.finding import normalize_path_template
from harness_dast.domain.zap_alert import Severity

TECHNIQUE_LABEL: Final[dict[AuthzTechnique, str]] = {
    "authz_cors": "Política CORS permissiva",
    "authz_horizontal": "Acesso horizontal entre contas do mesmo papel (BOLA/IDOR)",
    "authz_vertical": "Acesso vertical: papel menor chama operação de papel maior (BFLA)",
    "authz_excessive_data": "Exposição excessiva de dados (campos fora do esquema)",
    "authz_mass_assignment": "Atribuição em massa (campo extra aceito)",
    "authz_anonymous_access": "Acesso sem login",
    "authz_tampered_token": "Token adulterado aceito",
    "authz_horizontal_write": "Escrita em recurso de outra conta do mesmo papel (BOLA)",
    "authz_access_matrix": "Papel que a tabela quem pode o quê proíbe executou a operação (BFLA)",
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


def identifier_severity(path_template: str, identifiers: tuple[IdentifierRef, ...]) -> Severity:
    """Severidade do BOLA de leitura: alta, ou média se só há identificador de consulta sem pista.

    Identificador no caminho, ou de consulta com `owned_hint` (o valor aparece como
    identificador de caminho da mesma conta dona), é alta. Só o NOME indicando identificador
    de consulta (`name_only`) é média: filtro público parecido com `?categoriaId=3` é o falso
    alarme típico (o remédio é `authz.public_operations`).
    """
    if "{" in path_template or not identifiers:
        return "high"
    return "high" if any(ref.confidence == "owned_hint" for ref in identifiers) else "medium"


def _identifier_evidence(identifiers: tuple[IdentifierRef, ...]) -> str:
    if not identifiers:
        return ""
    names = ", ".join(f"`{ref.name}`" for ref in identifiers)
    hinted = any(ref.confidence == "owned_hint" for ref in identifiers)
    how = (
        "o valor também aparece como identificador de caminho da conta dona"
        if hinted
        else "só o nome indica identificador"
    )
    return f" Identificador na consulta: {names} ({how})."


def horizontal_finding(
    *,
    product: str,
    operation_id: str,
    method: str,
    path_template: str,
    actor: tuple[str, str | None],
    owner: tuple[str, str | None],
    statuses: tuple[int, int],
    identifiers: tuple[IdentifierRef, ...] = (),
) -> AuthzFinding:
    """Achado de BOLA: outra conta do mesmo papel leu o recurso com o mesmo conteúdo.

    `identifiers` são os de CONSULTA (ADR 0042): entram em `fields` como `query:<nome>` e na
    severidade. Sem eles (identificador só no caminho) `fields` fica vazio e o fingerprint
    é o de sempre.
    """
    where = " (identificador na consulta)" if identifiers else ""
    return build_finding(
        product=product,
        technique="authz_horizontal",
        title=f"{method.upper()} {normalize_path_template(path_template)} devolve o recurso "
        f"de uma conta a outra do mesmo papel{where}",
        severity=identifier_severity(path_template, identifiers),
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=owner,
        statuses=statuses,
        fields=tuple(f"query:{ref.name}" for ref in identifiers),
        evidence=(
            f"A conta {owner[0]} e a conta {actor[0]} (mesmo papel) receberam resposta "
            f"{statuses[0]} e {statuses[1]} com corpo equivalente para o mesmo pedido."
            + _identifier_evidence(identifiers)
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


SOURCE_TEXT: Final[dict[CandidateSource, str]] = {
    "declared": "campo declarado em authz.mass_assignment_fields",
    "readonly_in_input": "campo que o OpenAPI marca como somente leitura no corpo de entrada",
    "response_only": "campo que o OpenAPI só mostra na resposta, não no corpo de entrada",
    "name_in_input": "campo do corpo de entrada com nome de privilégio",
}
"""De onde veio o campo testado, em português (vai no título e na evidência do achado)."""

MassObservation = Literal["update", "created_read", "post_response"]
_OBSERVED: Final[dict[MassObservation, str]] = {
    "update": "a leitura seguinte do recurso",
    "created_read": "a leitura do recurso criado",
    "post_response": "a resposta do próprio POST",
}


# Passa de 40 linhas porque quase todas são os textos fixos do achado (título, evidência, correção).
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
    source: CandidateSource = "declared",
    kind: CandidateKind = "other",
    observed_in: MassObservation = "update",
) -> AuthzFinding:
    """Achado de atribuição em massa: o campo extra enviado mudou o estado do recurso.

    A severidade é alta para o campo declarado e para as classes `privilege` e `balance`, e média
    para as demais (`mass_severity`). Num `POST` não há o que restaurar: o recurso criado com o
    campo atribuído permanece no alvo, e a evidência diz isso.
    """
    created = method.upper() == "POST"
    if created:
        state = (
            "Nada foi restaurado: o recurso criado com o campo atribuído continua no ambiente "
            "de teste (use `hdast cleanup` ou o reset do ambiente)."
        )
    else:
        state = {
            True: "O valor anterior foi restaurado e conferido.",
            False: "Não foi possível restaurar o valor anterior: confira o estado da conta.",
            None: "Não havia valor anterior para restaurar.",
        }[restored]
    origin = "" if source == "declared" else f" (origem: {SOURCE_TEXT[source]})"
    action = "ao criar o recurso " if created else ""
    return build_finding(
        product=product,
        technique="authz_mass_assignment",
        title=f"{method.upper()} {normalize_path_template(path_template)} aceita o campo "
        f"extra '{sent_field}'{'' if source == 'declared' else ' (campo tirado do OpenAPI)'}",
        severity=mass_severity(source, kind),
        operation_id=operation_id,
        method=method,
        path_template=path_template,
        actor=actor,
        owner=None,
        statuses=(None, status),
        fields=(sent_field, *(path for path in changed if path != sent_field)),
        evidence=(
            f"Ao enviar o campo '{sent_field}' {action}junto do corpo válido{origin}, "
            f"{_OBSERVED[observed_in]} mostrou o valor injetado em: {', '.join(changed)}. "
            f"{state}"
        ),
        description=(
            "A API copia campos do corpo para o objeto sem lista de campos permitidos; um "
            "usuário comum pode alterar atributos que não deveria (por exemplo, o papel)."
        ),
        solution=(
            "Usar um objeto de entrada com só os campos editáveis e ignorar ou recusar os "
            "demais; nunca ligar o corpo diretamente à entidade."
        ),
        candidate_source=source,
    )
