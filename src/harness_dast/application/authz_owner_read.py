"""Executa só GETs de dono pelo emissor guardado existente; corpos vivem em memória."""

from harness_dast.application.authz_sender import CheckContext, CheckResult, Reply, problem_note
from harness_dast.domain.authz_compare import bodies_equivalent, is_success_status
from harness_dast.domain.authz_created import parse_unique_json
from harness_dast.domain.authz_findings import horizontal_finding
from harness_dast.domain.authz_owner_ids import object_identity, owner_inventory
from harness_dast.domain.authz_owner_plan import (
    MAX_OWNER_OBJECTS,
    OwnerReadTask,
    owner_exchange,
    owner_note,
    owner_verdict,
)
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.probe_exchange import ExchangeRecord


def run_owner_reads(ctx: CheckContext, plan: Planned[OwnerReadTask], out: CheckResult) -> None:
    """Acrescenta provas limitadas e lacunas ao resultado horizontal vivo, sem escrita."""
    out.not_tested.extend(plan.not_tested)
    objects = 0
    if plan.tasks:
        out.message = _count(len(plan.tasks), objects)
    for task in plan.tasks:
        identities = _identities(ctx, task, out)
        if len(identities) > MAX_OWNER_OBJECTS:
            out.not_tested.append(owner_note(task.operation, "budget_exhausted"))
        for identity in identities[:MAX_OWNER_OBJECTS]:
            objects += 1
            out.candidates += 1
            out.message = _count(len(plan.tasks), objects)
            _compare(ctx, task, identity, out)


def _count(tasks: int, objects: int) -> str:
    return (
        f"Leitura de dono: {tasks} operação/par; {objects} objeto(s) "
        f"tentado(s); teto {MAX_OWNER_OBJECTS} por operação/par, somente GET."
    )


def _identities(ctx: CheckContext, task: OwnerReadTask, out: CheckResult) -> tuple[str, ...]:
    if task.collection is None:
        return task.identifiers
    operation = task.collection
    own = owner_exchange(operation, task.owner[0], operation.path)
    peer = owner_exchange(operation, task.actor[0], operation.path)
    first = ctx.sender.send(own, task.owner[0], tag="owner:collection:")
    if not _available(first, own, task, out):
        return ()
    own_ids = owner_inventory(first.body, task.parameter)
    if own_ids is None:
        out.not_tested.append(owner_note(task.operation, "ambiguous_identifier"))
        return ()
    if not own_ids:
        out.not_tested.append(owner_note(task.operation, "owner_collection_empty"))
        return ()
    second = ctx.sender.send(peer, task.actor[0], tag="owner:collection:")
    if not _available(second, peer, task, out):
        return ()
    peer_ids = owner_inventory(second.body, task.parameter)
    if peer_ids is None or set(own_ids) & set(peer_ids):
        out.not_tested.append(owner_note(task.operation, "ambiguous_identifier"))
        return ()
    return own_ids


def _available(
    reply: Reply, exchange: ExchangeRecord, task: OwnerReadTask, out: CheckResult
) -> bool:
    if reply.problem is not None:
        # A lacuna pertence ao GET de item, mesmo quando a recusa ocorreu na coleção.
        note = problem_note("horizontal", exchange, reply)
        out.not_tested.append(
            note.model_copy(
                update={"operation_id": task.operation.operation_id, "path": task.operation.path}
            )
        )
        return False
    if not is_success_status(reply.status):
        out.not_tested.append(owner_note(task.operation, "owner_collection_unavailable"))
        return False
    return True


def _compare(ctx: CheckContext, task: OwnerReadTask, identity: str, out: CheckResult) -> None:
    operation = task.operation
    target = operation.path.rsplit("/", 1)[0] + "/" + identity
    exchange = owner_exchange(operation, task.owner[0], target)
    base = ctx.sender.send(exchange, task.owner[0], tag="owner:baseline:")
    if base.problem is not None:
        out.not_tested.append(problem_note("horizontal", exchange, base))
        return
    base_identity = object_identity(parse_unique_json(base.body), task.parameter) == identity
    if not is_success_status(base.status) or not base_identity:
        out.not_tested.append(owner_note(operation, "baseline_failed"))
        return
    replay = ctx.sender.send(exchange, task.actor[0], tag="owner:replay:")
    if replay.problem is not None:
        out.not_tested.append(problem_note("horizontal", exchange, replay))
        return
    verdict = owner_verdict(
        base.status,
        replay.status,
        same=bodies_equivalent(base.body, replay.body, ctx.volatile),
        baseline_identity=base_identity,
        replay_identity=object_identity(parse_unique_json(replay.body), task.parameter) == identity,
    )
    _record(ctx, task, verdict, base, replay, out)


def _record(
    ctx: CheckContext,
    task: OwnerReadTask,
    verdict: str,
    base: Reply,
    replay: Reply,
    out: CheckResult,
) -> None:
    if verdict == "inconclusive":
        out.not_tested.append(owner_note(task.operation, verdict))
        return
    out.tested += 1
    if verdict == "finding" and base.status is not None and replay.status is not None:
        out.findings.append(
            horizontal_finding(
                product=ctx.settings.product,
                operation_id=task.operation.operation_id,
                method="GET",
                path_template=task.operation.path,
                actor=task.actor,
                owner=task.owner,
                statuses=(base.status, replay.status),
            )
        )
