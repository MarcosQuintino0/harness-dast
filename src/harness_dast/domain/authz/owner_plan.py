"""Plano puro de leitura de dono independente do roteamento de alcance (ADR 0082)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.authz.compare import is_success_status, judge_replay
from harness_dast.domain.authz.owner_ids import (
    owner_collection,
    owner_parameter,
    recorded_owner_ids,
)
from harness_dast.domain.authz.plan import Planned
from harness_dast.domain.authz.result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

MAX_OWNER_OBJECTS: Final = 2
OWNER_ACTIONS: Final = MappingProxyType(
    {
        "owner_read_unsupported": (
            "Declare um único identificador final escalar e leituras "
            "sem outros parâmetros obrigatórios."
        ),
        "no_peer_account": "Declare duas contas do mesmo papel não compartilhado na carta.",
        "public_operation": (
            "Operação pública declarada no perfil; a leitura de dono não é comparada."
        ),
        "owner_collection_missing": (
            "Não há coleção da conta que traga o identificador; declare a coleção no contrato "
            "ou alcance uma criação pela conta dona."
        ),
        "owner_collection_empty": (
            "A coleção da conta dona está vazia; disponibilize recursos sintéticos para essa conta."
        ),
        "owner_collection_unavailable": (
            "A coleção da conta não pôde ser lida; confira sessão, contrato e disponibilidade "
            "sem ampliar o escopo."
        ),
        "ambiguous_identifier": (
            "Identificador inválido, repetido ou compartilhado entre contas; forneça recursos "
            "sintéticos distintos e identidade inequívoca no contrato."
        ),
        "baseline_failed": (
            "A conta dona não confirmou 2xx com o mesmo identificador; confira seus recursos "
            "sintéticos antes de repetir."
        ),
        "inconclusive": (
            "A repetição não comprovou proteção nem acesso equivalente ao mesmo objeto; "
            "confira a regra do produto."
        ),
        "budget_exhausted": (
            "A amostra foi limitada a dois objetos por operação e par; "
            "os demais não foram testados."
        ),
    }
)


@dataclass(frozen=True)
class OwnerReadTask:
    """GET de item, par determinístico e fontes já observadas ou coleção irmã."""

    operation: Operation
    parameter: Parameter
    owner: tuple[str, str]
    actor: tuple[str, str]
    collection: Operation | None
    identifiers: tuple[str, ...] = ()


def owner_exchange(operation: Operation, account: str, target: str) -> ExchangeRecord:
    """GET estrutural; status zero é sentinela, nunca prova sucesso da linha de base."""
    return ExchangeRecord(
        operation_id=operation.operation_id,
        method="GET",
        path=operation.path,
        target=target,
        account=account,
        status=0,
    )


def owner_note(operation: Operation, reason: str) -> AuthzNotTested:
    """Lacuna estável com operação e ação, sem valores do alvo."""
    return AuthzNotTested(
        check="horizontal",
        operation_id=operation.operation_id,
        method="GET",
        path=operation.path,
        reason=reason,
        message=OWNER_ACTIONS[reason],
    )


def owner_pair(roles: Mapping[str, str], shared: Sequence[str]) -> tuple[str, str] | None:
    """Primeiras duas contas do primeiro papel não compartilhado com par, na ordem do perfil."""
    for alias, role in roles.items():
        peers = [account for account, other in roles.items() if other == role and account != alias]
        if role not in shared and peers:
            return alias, peers[0]
    return None


def plan_owner_reads(
    operations: Sequence[Operation],
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    public: frozenset[str],
    shared: Sequence[str],
) -> Planned[OwnerReadTask]:
    """Planeja GETs com marcador ainda sem leitura provada por conta elegível.

    Não envia nada, não usa o account_map como autorização e não autoriza escrita.
    """
    pair = owner_pair(roles, shared)
    tasks: list[OwnerReadTask] = []
    notes: list[AuthzNotTested] = []
    for operation in operations:
        if operation.method != "get" or not operation.path_placeholders:
            continue
        if _has_owner(operation, exchanges, roles, shared):
            continue
        task, reason = _owner_task(operation, operations, exchanges, roles, pair, public)
        if task is not None:
            tasks.append(task)
        elif reason is not None:
            notes.append(owner_note(operation, reason))
    return Planned(tuple(tasks), tuple(notes))


def _has_owner(
    operation: Operation,
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    shared: Sequence[str],
) -> bool:
    for item in exchanges:
        role = roles.get(item.account)
        if (
            item.operation_id == operation.operation_id
            and item.method == "GET"
            and is_success_status(item.status)
            and role is not None
            and role not in shared
            and sum(other == role for other in roles.values()) >= 2
        ):
            return True
    return False


def _owner_task(
    operation: Operation,
    operations: Sequence[Operation],
    exchanges: Sequence[ExchangeRecord],
    roles: Mapping[str, str],
    pair: tuple[str, str] | None,
    public: frozenset[str],
) -> tuple[OwnerReadTask | None, str | None]:
    if operation.operation_id in public:
        return None, "public_operation"
    parameter = owner_parameter(operation)
    if parameter is None:
        return None, "owner_read_unsupported"
    if pair is None:
        return None, "no_peer_account"
    collections = [op for op in operations if owner_collection(op, operation, parameter)]
    if len(collections) > 1:
        return None, "ambiguous_identifier"
    collection = collections[0] if collections else None
    identifiers, reason = (
        _known_ids(operation, parameter, pair, exchanges) if collection is None else ((), None)
    )
    if reason is not None:
        return None, reason
    return OwnerReadTask(
        operation,
        parameter,
        (pair[0], roles[pair[0]]),
        (pair[1], roles[pair[1]]),
        collection,
        identifiers,
    ), None


def _known_ids(
    operation: Operation,
    parameter: Parameter,
    pair: tuple[str, str],
    exchanges: Sequence[ExchangeRecord],
) -> tuple[tuple[str, ...], str | None]:
    own = recorded_owner_ids(operation, parameter, pair[0], exchanges)
    peer = recorded_owner_ids(operation, parameter, pair[1], exchanges)
    if own is None or peer is None or set(own) & set(peer):
        return (), "ambiguous_identifier"
    if not own:
        return (), "owner_collection_missing"
    return own, None


def owner_verdict(
    baseline: int | None,
    replay: int | None,
    *,
    same: bool,
    baseline_identity: bool,
    replay_identity: bool,
) -> str:
    """Só 401/403/404 protegem; achado exige identidade e equivalência com base 2xx."""
    if not is_success_status(baseline) or not baseline_identity:
        return "baseline_failed"
    if replay in {401, 403, 404}:
        return "protected"
    verdict = judge_replay(baseline, replay, equivalent=same and replay_identity)
    return "finding" if verdict == "allowed_equivalent" else "inconclusive"


def visible_authz_notes(notes: Sequence[AuthzNotTested], limit: int) -> tuple[AuthzNotTested, ...]:
    """Não oculta lacunas horizontais por truncamento da apresentação geral."""
    horizontal = tuple(n for n in notes if n.check == "horizontal")
    other = tuple(n for n in notes if n.check != "horizontal")
    return (*horizontal, *other[: max(0, limit - len(horizontal))])
