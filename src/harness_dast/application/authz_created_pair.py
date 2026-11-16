"""Cria recurso sintético e compara leitura das duas contas pela cerca."""

import json

from harness_dast.application.authz_sender import (
    CheckContext,
    CheckResult,
    Reply,
    inconclusive,
    note,
    problem_note,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_compare import bodies_equivalent, is_success_status, parse_json
from harness_dast.domain.authz_created import created_identifier, created_read_exchange
from harness_dast.domain.authz_findings import horizontal_finding
from harness_dast.domain.authz_flow_bindings import bindings_from_proven_body
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_created_pair import CreatedPairTask
from harness_dast.domain.authz_plan_mass import MAX_MASS_REQUESTS
from harness_dast.domain.errors import ConfigError, TargetError
from harness_dast.domain.probe_exchange import ExchangeRecord


def run_created_pairs(ctx: CheckContext, plan: Planned[CreatedPairTask], out: CheckResult) -> None:
    """Executa criações autorizadas, confirma a dona e só então compara a conta par."""
    out.not_tested.extend(plan.not_tested)
    out.candidates += len(plan.tasks)
    for task in plan.tasks:
        _one(ctx, task, out)


def _one(ctx: CheckContext, task: CreatedPairTask, out: CheckResult) -> None:
    post = task.post
    if ctx.shared_writes >= MAX_MASS_REQUESTS:
        out.not_tested.append(
            note("horizontal", post, "budget_exhausted", "Teto de escrita compartilhado atingido.")
        )
        return
    body = _new_body(ctx, post, out)
    if body is None:
        return
    target = _confirm_absent(ctx, task, body, out)
    if target is None:
        return
    original = parse_json((post.body or "").encode())
    prior = original if isinstance(original, dict) else {}
    identifier = target.target.rsplit("/", 1)[-1]
    builder = ctx.settings.builder
    markers: dict[str, JsonValue] = {
        name: value
        for name, value in body.items()
        if isinstance(value, str | int | bool)
        and str(value) != identifier
        and name in prior
        and prior[name] != value
        and builder is not None
        and builder.reuses_unique_body_value(post.operation_id, {name: value}, {name: value})
    }
    if not markers:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_marker_unavailable",
                "Não há marcador novo independente para confirmar a leitura após o POST.",
            )
        )
        return
    if ctx.settings.counter_checkpoint is not None and ctx.settings.builder is not None:
        ctx.settings.counter_checkpoint(ctx.settings.builder.next_unique_counter)
    ctx.shared_writes += 1
    out.writes += 1
    reply = ctx.sender.send(
        post, task.owner[0], body=body, with_body=True, tag="pair:", max_attempts=1
    )
    _check_created(ctx, task, out, reply, target, markers)


def _confirm_absent(
    ctx: CheckContext, task: CreatedPairTask, body: dict[str, JsonValue], out: CheckResult
) -> ExchangeRecord | None:
    identifier = created_identifier(
        location=None,
        body=json.dumps(body).encode(),
        reader=task.read,
        base_url=ctx.settings.base_url,
    )
    target = created_read_exchange(task.read, identifier) if identifier else None
    if target is None:
        out.not_tested.append(
            note(
                "horizontal",
                task.post,
                "new_identifier_unavailable",
                "O corpo novo não fornece identificador para conferir ausência antes da criação.",
            )
        )
        return None
    before = ctx.sender.send(target, task.owner[0], tag="pair:", max_attempts=1)
    if before.problem is not None:
        out.not_tested.append(problem_note("horizontal", target, before))
        return None
    if before.status != 404:
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "created_target_preexisting"
                if _successful(ctx, before)
                else "created_absence_unconfirmed",
                "A leitura anterior não confirmou ausência do identificador (HTTP 404).",
            )
        )
        return None
    peer_before = ctx.sender.send(target, task.actor[0], tag="pair:", max_attempts=1)
    if peer_before.problem is not None:
        out.not_tested.append(problem_note("horizontal", target, peer_before))
        return None
    if peer_before.status != 404:
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "peer_absence_unconfirmed",
                "A conta par não confirmou ausência visível antes da criação (HTTP 404).",
            )
        )
        return None
    return target


def _new_body(
    ctx: CheckContext, post: ExchangeRecord, out: CheckResult
) -> dict[str, JsonValue] | None:
    builder = ctx.settings.builder
    operation = ctx.settings.operations.get(post.operation_id)
    if builder is None or operation is None:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "Não foi possível gerar dados novos; confira as regras e rode um novo probe "
                "se o registro for anterior ao contador de valores únicos.",
            )
        )
        return None
    try:
        original = parse_json((post.body or "").encode())
        bindings = bindings_from_proven_body(ctx.settings.flows, post.operation_id, original)
        built = builder.build(operation, bindings)
        for _ in range(7):
            if built.body != original and not builder.reuses_unique_body_value(
                post.operation_id, original, built.body, bound_fields=frozenset(bindings.fields)
            ):
                break
            built = builder.build(operation, bindings)
    except TargetError:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "flow_binding_unavailable",
                "O corpo provado não contém uma referência declarada em flows.yml; criação pulada.",
            )
        )
        return None
    except ConfigError:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "As regras do perfil não geraram um corpo para a criação.",
            )
        )
        return None
    if (
        not isinstance(built.body, dict)
        or built.body == original
        or builder.reuses_unique_body_value(
            post.operation_id, original, built.body, bound_fields=frozenset(bindings.fields)
        )
    ):
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "A criação não gerou corpo JSON novo; ajuste data-rules.yml.",
            )
        )
        return None
    return built.body


def _check_created(
    ctx: CheckContext,
    task: CreatedPairTask,
    out: CheckResult,
    reply: Reply,
    expected: ExchangeRecord,
    markers: dict[str, JsonValue],
) -> None:
    post = task.post
    if reply.problem:
        out.not_tested.append(problem_note("horizontal", post, reply))
        return
    if not _successful(ctx, reply):
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "create_failed",
                f"A criação não foi confirmada (status {reply.status}); confira o ambiente.",
            )
        )
        return
    identifier = created_identifier(
        location=reply.location, body=reply.body, reader=task.read, base_url=ctx.settings.base_url
    )
    target = created_read_exchange(task.read, identifier) if identifier else None
    if target is None:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "created_identifier_unavailable",
                "A resposta não identificou o recurso criado de forma segura.",
            )
        )
        return
    if target.target != expected.target or target.target.split("?", 1)[0] in task.existing_targets:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "created_target_preexisting",
                "O identificador já aparecia em leitura provada; não é possível confirmar que "
                "o objeto é novo. A operação pode ter deixado recurso no ambiente.",
            )
        )
        return
    _compare(ctx, task, target, out, markers)


def _successful(ctx: CheckContext, reply: Reply) -> bool:
    if not is_success_status(reply.status):
        return False
    rule = ctx.settings.success.json_field_absent_or_not_equal
    return rule is None or not rule.is_failure(parse_json(reply.body))


def _compare(
    ctx: CheckContext,
    task: CreatedPairTask,
    target: ExchangeRecord,
    out: CheckResult,
    markers: dict[str, JsonValue],
) -> None:
    owner = ctx.sender.send(target, task.owner[0], tag="pair:")
    if owner.problem:
        out.not_tested.append(problem_note("horizontal", target, owner))
        return
    if not _successful(ctx, owner) or not owner.body.strip():
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "created_owner_read_failed",
                "A conta criadora não conseguiu confirmar a leitura do recurso criado.",
            )
        )
        return
    observed = parse_json(owner.body)
    if not isinstance(observed, dict) or not any(
        name in observed and type(observed[name]) is type(value) and observed[name] == value
        for name, value in markers.items()
    ):
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "new_marker_unconfirmed",
                "A leitura da dona não confirmou o marcador novo enviado na criação.",
            )
        )
        return
    out.created += 1
    peer = ctx.sender.send(target, task.actor[0], tag="pair:")
    if peer.problem:
        out.not_tested.append(problem_note("horizontal", target, peer))
        return
    if peer.status in (401, 403, 404):
        out.tested += 1
        return
    if not _successful(ctx, peer):
        out.not_tested.append(inconclusive("horizontal", target, peer))
        return
    if not bodies_equivalent(owner.body, peer.body, ctx.volatile):
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "created_read_different",
                "As respostas diferem; "
                "não foi possível confirmar que a conta par recebeu o mesmo recurso.",
            )
        )
        return
    if owner.status is None or peer.status is None:
        return
    out.tested += 1
    out.findings.append(
        horizontal_finding(
            product=ctx.settings.product,
            operation_id=target.operation_id,
            method="GET",
            path_template=target.path,
            actor=task.actor,
            owner=task.owner,
            statuses=(owner.status, peer.status),
        )
    )
