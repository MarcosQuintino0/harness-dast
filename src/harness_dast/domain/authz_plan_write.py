"""Plano da escrita em recurso de outra conta (`horizontal_write`, ADR 0042).

Escolhe, entre os pedidos que o `probe` já provou, cada `PUT` e `PATCH` com corpo JSON (objeto) e
identificador de objeto no caminho ou na consulta, que não é público, tem uma conta par do mesmo
papel e um `GET` provado do mesmo recurso (o leitor que confirma o efeito: nunca se escreve às
cegas). `POST` não entra (criar não é "recurso de outra conta") e `DELETE` nunca. A conta que
escreve é UMA conta par (a primeira do mesmo papel), para sujar o mínimo. Só roda com
`allow_writes`: quem decide é o chamador. Este módulo é puro.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_compare import is_success_status
from harness_dast.domain.authz_identifiers import find_identifiers
from harness_dast.domain.authz_plan import (
    Planned,
    no_identifier_note,
    skip_note,
    unique_exchanges,
)
from harness_dast.domain.authz_plan_mass import is_json_object, update_reader
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

WRITE_METHODS: Final = frozenset({"PUT", "PATCH"})
MAX_WRITE_TASKS: Final = 50
"""Teto de candidatos de escrita em outra conta por execução."""


@dataclass(frozen=True)
class WriteTask:
    """Escrever, com a conta `actor`, no recurso da conta dona de `exchange`.

    Attributes:
        exchange: O `PUT` ou `PATCH` provado (da conta dona).
        owner: Apelido e papel da conta dona (lê antes e depois e restaura).
        actor: Apelido e papel da conta par que tenta escrever.
        read: `GET` provado do mesmo recurso, da conta dona (confirma o efeito).
        properties: Esquema de entrada por campo (do OpenAPI), quando declarado.
    """

    exchange: ExchangeRecord
    owner: tuple[str, str]
    actor: tuple[str, str]
    read: ExchangeRecord
    properties: Mapping[str, Schema] = field(default_factory=dict)


def input_properties(operation: Operation | None) -> dict[str, Schema]:
    """Campos do corpo de entrada declarados no OpenAPI (vazio se a operação não os declara)."""
    if operation is None or operation.request_body is None:
        return {}
    media = operation.request_body.preferred()
    if media is None or media.body_schema is None:
        return {}
    return dict(media.body_schema.properties)


def plan_horizontal_write(
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    public: frozenset[str],
    operations: Sequence[Operation] = (),
    id_parameters: Sequence[str] = (),
    budget: int = MAX_WRITE_TASKS,
) -> Planned[WriteTask]:
    """Escrita em outra conta: cada `PUT` ou `PATCH` com identificador, leitor e conta par.

    Args:
        exchanges: Pedidos com sucesso do `probe`.
        roles: Papel de cada conta (apelido -> papel), na ordem do perfil.
        public: Operações marcadas como públicas ou compartilhadas.
        operations: Operações do OpenAPI (parâmetros de consulta e esquema de entrada).
        id_parameters: `authz.id_parameters`.
        budget: Teto de candidatos; o excedente vai para `not_tested`.
    """
    by_id = {op.operation_id: op for op in operations}
    reads = [e for e in exchanges if e.method == "GET" and is_success_status(e.status)]
    tasks: list[WriteTask] = []
    skips: list[AuthzNotTested] = []
    for item in unique_exchanges([e for e in exchanges if e.method in WRITE_METHODS]):
        operation = by_id.get(item.operation_id)
        refusal = _refusal(item, operation, exchanges, public, id_parameters)
        chosen = refusal or _task(item, operation, roles, reads)
        if isinstance(chosen, AuthzNotTested):
            skips.append(chosen)
        elif len(tasks) >= budget:
            skips.append(_budget_note(item, budget))
        else:
            tasks.append(chosen)
    return Planned(tuple(tasks), tuple(skips))


def _refusal(
    item: ExchangeRecord,
    operation: Operation | None,
    exchanges: Sequence[ExchangeRecord],
    public: frozenset[str],
    id_parameters: Sequence[str],
) -> AuthzNotTested | None:
    if item.operation_id in public:
        return skip_note("horizontal_write", item, "public_operation", "Marcada como pública.")
    if not is_json_object(item.body):
        return skip_note(
            "horizontal_write",
            item,
            "no_json_body",
            "O probe não guardou um corpo JSON (objeto) para esta operação.",
        )
    scan = find_identifiers(operation, item, exchanges, id_parameters)
    if not scan.refs:
        return no_identifier_note("horizontal_write", item, scan.ambiguous)
    return None


def _task(
    item: ExchangeRecord,
    operation: Operation | None,
    roles: Mapping[str, str],
    reads: Sequence[ExchangeRecord],
) -> WriteTask | AuthzNotTested:
    owner_role = roles.get(item.account)
    peers = [a for a, r in roles.items() if r == owner_role and a != item.account]
    if owner_role is None or not peers:
        return skip_note(
            "horizontal_write",
            item,
            "no_peer_account",
            f"Não há outra conta do papel '{owner_role}' no perfil; cadastre uma segunda conta "
            "do mesmo papel em auth.accounts.",
        )
    reader = update_reader(item, reads)
    if reader is None:
        return skip_note(
            "horizontal_write",
            item,
            "no_read_to_confirm",
            "Não há GET provado do mesmo recurso, da conta dona, para confirmar o efeito; "
            "nunca se escreve às cegas.",
        )
    return WriteTask(
        item,
        (item.account, owner_role),
        (peers[0], owner_role),
        reader,
        input_properties(operation),
    )


def _budget_note(item: ExchangeRecord, budget: int) -> AuthzNotTested:
    return skip_note(
        "horizontal_write",
        item,
        "budget_exhausted",
        f"O teto de {budget} candidatos de escrita em outra conta por execução foi atingido; "
        "esta operação ficou sem teste.",
    )
