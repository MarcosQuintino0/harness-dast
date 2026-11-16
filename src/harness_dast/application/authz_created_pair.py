"""Cria recurso sintético e compara leitura das duas contas pela cerca."""

from harness_dast.application.authz_sender import (
    CheckContext,
    CheckResult,
    inconclusive,
    note,
    problem_note,
)
from harness_dast.domain.authz_compare import bodies_equivalent, is_success_status, parse_json
from harness_dast.domain.authz_created import created_identifier, created_read_exchange
from harness_dast.domain.authz_findings import horizontal_finding
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_created_pair import CreatedPairTask
from harness_dast.domain.authz_plan_mass import MAX_MASS_REQUESTS
from harness_dast.domain.errors import ConfigError
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
    builder = ctx.settings.builder
    operation = ctx.settings.operations.get(post.operation_id)
    if builder is None or operation is None:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "Não foi possível gerar dados novos pelas regras do perfil.",
            )
        )
        return
    try:
        built = builder.build(operation)
    except ConfigError:
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "As regras do perfil não geraram um corpo para a criação.",
            )
        )
        return
    if not isinstance(built.body, dict) or built.body == parse_json((post.body or "").encode()):
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "new_data_unavailable",
                "A criação não gerou corpo JSON novo; ajuste data-rules.yml.",
            )
        )
        return
    ctx.shared_writes += 1
    out.writes += 1
    reply = ctx.sender.send(post, task.owner[0], body=built.body, with_body=True, tag="pair:")
    if reply.problem:
        out.not_tested.append(problem_note("horizontal", post, reply))
        return
    if not is_success_status(reply.status):
        out.not_tested.append(
            note(
                "horizontal",
                post,
                "create_failed",
                f"A conta criadora não criou o recurso (status {reply.status}).",
            )
        )
        return
    out.created += 1
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
    _compare(ctx, task, target, out)


def _compare(
    ctx: CheckContext, task: CreatedPairTask, target: ExchangeRecord, out: CheckResult
) -> None:
    owner = ctx.sender.send(target, task.owner[0], tag="pair:")
    if owner.problem:
        out.not_tested.append(problem_note("horizontal", target, owner))
        return
    if not is_success_status(owner.status) or not owner.body.strip():
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "created_owner_read_failed",
                "A conta criadora não conseguiu confirmar a leitura do recurso criado.",
            )
        )
        return
    peer = ctx.sender.send(target, task.actor[0], tag="pair:")
    if peer.problem:
        out.not_tested.append(problem_note("horizontal", target, peer))
        return
    if peer.status in (401, 403, 404):
        out.tested += 1
        return
    if not is_success_status(peer.status):
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
