"""Plano do teste de autorização: o que repetir, com qual conta, e o que fica sem teste.

O plano só ESCOLHE entre pedidos que o `probe` já provou com sucesso (`ExchangeRecord`): não
inventa caminho, não troca método e não adivinha identificador. Cada pedido recusado pelo plano
vira um `AuthzNotTested` com o motivo, para que a ausência de achado nunca seja confundida com
"testado e seguro". Este módulo é puro.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from harness_dast.domain.authz_compare import is_success_status
from harness_dast.domain.authz_config import AuthzCheck
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

MAX_PEERS: Final = 2
WRITE_METHODS: Final = frozenset({"PUT", "PATCH"})


@dataclass(frozen=True)
class ReplayTask:
    """Repetir `exchange` (da conta dona) com a conta `actor`.

    Attributes:
        exchange: Pedido gravado pelo `probe`.
        owner: Apelido e papel da conta que o enviou.
        actor: Apelido e papel da conta que vai repeti-lo.
    """

    exchange: ExchangeRecord
    owner: tuple[str, str]
    actor: tuple[str, str]


@dataclass(frozen=True)
class MassTask:
    """Enviar campos extras num `PUT` ou `PATCH` provado pelo `probe`.

    Attributes:
        exchange: O pedido de atualização.
        read: Leitura (`GET` do mesmo modelo de caminho, mesma conta) para conferir o efeito,
            ou `None` (vale a própria resposta da atualização).
    """

    exchange: ExchangeRecord
    read: ExchangeRecord | None


@dataclass(frozen=True)
class Planned[T]:
    """Tarefas escolhidas e o que ficou sem teste."""

    tasks: tuple[T, ...]
    not_tested: tuple[AuthzNotTested, ...]


def _skip(
    check: AuthzCheck, exchange: ExchangeRecord | None, reason: str, message: str
) -> AuthzNotTested:
    return AuthzNotTested(
        check=check,
        operation_id=exchange.operation_id if exchange else None,
        method=exchange.method if exchange else None,
        path=exchange.path if exchange else None,
        reason=reason,
        message=message,
    )


def _unique(exchanges: Sequence[ExchangeRecord]) -> tuple[ExchangeRecord, ...]:
    seen: set[tuple[str, str, str]] = set()
    found: list[ExchangeRecord] = []
    for item in exchanges:
        key = (item.method, item.target, item.account)
        if key not in seen:
            seen.add(key)
            found.append(item)
    return tuple(found)


def plan_horizontal(
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    public: frozenset[str],
) -> Planned[ReplayTask]:
    """BOLA: cada `GET` com identificador no caminho, repetido por contas do MESMO papel.

    Args:
        exchanges: Pedidos com sucesso do `probe`.
        roles: Papel de cada conta (apelido -> papel), na ordem do perfil.
        public: Operações marcadas como públicas ou compartilhadas.
    """
    tasks: list[ReplayTask] = []
    skips: list[AuthzNotTested] = []
    for item in _unique([e for e in exchanges if e.method == "GET"]):
        if item.operation_id in public:
            skips.append(
                _skip("horizontal", item, "public_operation", "Marcada como pública no perfil.")
            )
            continue
        if "{" not in item.path:
            skips.append(
                _skip(
                    "horizontal",
                    item,
                    "no_path_parameter",
                    "Sem identificador no caminho: coleções não são comparadas entre contas.",
                )
            )
            continue
        owner_role = roles.get(item.account)
        peers = [a for a, r in roles.items() if r == owner_role and a != item.account]
        if owner_role is None or not peers:
            skips.append(
                _skip(
                    "horizontal",
                    item,
                    "no_peer_account",
                    f"Não há outra conta do papel '{owner_role}' no perfil; "
                    "cadastre uma segunda conta do mesmo papel em auth.accounts.",
                )
            )
            continue
        tasks.extend(
            ReplayTask(item, (item.account, owner_role), (peer, owner_role))
            for peer in peers[:MAX_PEERS]
        )
    return Planned(tuple(tasks), tuple(skips))


def plan_excessive(exchanges: Sequence[ExchangeRecord]) -> Planned[ExchangeRecord]:
    """Dado a mais: cada `GET` com sucesso (o esquema de resposta é conferido pelo caso de uso)."""
    return Planned(tuple(_unique([e for e in exchanges if e.method == "GET"])), ())


def plan_vertical(
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    role_order: Sequence[str],
    assigned: Callable[[ExchangeRecord], str | None],
    methods: frozenset[str],
    public: frozenset[str],
) -> Planned[ReplayTask]:
    """BFLA: operações atribuídas a um papel maior, repetidas por uma conta de cada papel menor.

    Args:
        exchanges: Pedidos com sucesso do `probe`.
        roles: Papel de cada conta (apelido -> papel), na ordem do perfil.
        role_order: Papéis do menor ao maior privilégio (`authz.role_order`).
        assigned: Apelido atribuído por regra EXPLÍCITA do `account_map`, ou `None`.
        methods: Métodos repetidos (`authz.vertical_methods`).
        public: Operações marcadas como públicas ou compartilhadas.
    """
    if not role_order:
        return Planned(
            (),
            (
                _skip(
                    "vertical",
                    None,
                    "no_role_order",
                    "Declare authz.role_order (papéis do menor ao maior) para testar acesso "
                    "vertical.",
                ),
            ),
        )
    rank = {role: index for index, role in enumerate(role_order)}
    tasks: list[ReplayTask] = []
    skips: list[AuthzNotTested] = []
    for item in _unique([e for e in exchanges if e.method in methods]):
        if item.operation_id in public:
            skips.append(
                _skip("vertical", item, "public_operation", "Marcada como pública no perfil.")
            )
            continue
        if assigned(item) != item.account:
            continue
        owner_role = roles.get(item.account)
        if owner_role not in rank:
            skips.append(
                _skip(
                    "vertical",
                    item,
                    "role_not_ranked",
                    f"O papel '{owner_role}' não está em authz.role_order.",
                )
            )
            continue
        lower = _lower_accounts(roles, rank, rank[owner_role])
        if not lower:
            skips.append(
                _skip(
                    "vertical",
                    item,
                    "no_lower_role_account",
                    "Não há conta de papel menor (em role_order) para repetir o pedido.",
                )
            )
            continue
        tasks.extend(ReplayTask(item, (item.account, owner_role), actor) for actor in lower)
    return Planned(tuple(tasks), tuple(skips))


def _lower_accounts(
    roles: Mapping[str, str], rank: Mapping[str, int], owner_rank: int
) -> tuple[tuple[str, str], ...]:
    chosen: dict[str, str] = {}
    for alias, role in roles.items():
        if role in rank and rank[role] < owner_rank and role not in chosen:
            chosen[role] = alias
    return tuple((alias, role) for role, alias in chosen.items())


def _is_json_object(text: str | None) -> bool:
    if text is None:
        return False
    try:
        return isinstance(json.loads(text), dict)
    except (ValueError, RecursionError):
        return False


def plan_mass_assignment(
    exchanges: Sequence[ExchangeRecord], public: frozenset[str]
) -> Planned[MassTask]:
    """Atribuição em massa: cada `PUT` ou `PATCH` com corpo JSON (objeto) provado pelo `probe`."""
    tasks: list[MassTask] = []
    skips: list[AuthzNotTested] = []
    reads = [e for e in exchanges if e.method == "GET" and is_success_status(e.status)]
    for item in _unique([e for e in exchanges if e.method in WRITE_METHODS]):
        if item.operation_id in public:
            skips.append(
                _skip("mass_assignment", item, "public_operation", "Marcada como pública.")
            )
        elif not _is_json_object(item.body):
            skips.append(
                _skip(
                    "mass_assignment",
                    item,
                    "no_json_body",
                    "O probe não guardou um corpo JSON (objeto) para esta operação.",
                )
            )
        else:
            same = [r for r in reads if r.path == item.path and r.account == item.account]
            exact = [r for r in same if r.target == item.target]
            chosen = exact or same
            tasks.append(MassTask(item, chosen[0] if chosen else None))
    return Planned(tuple(tasks), tuple(skips))
