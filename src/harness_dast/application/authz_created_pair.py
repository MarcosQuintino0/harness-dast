"""Cria recurso sintético e compara leitura das duas contas pela cerca.

Justificativa do tamanho (acima de 300 linhas): o par criado é um fluxo único e sequencial
(prova de ausência, criação, leitura da dona, comparação da outra conta e recibo), cujos passos
compartilham o mesmo `CheckContext` e a mesma ordem auditada; separar em módulos obrigaria passar
esse estado entre eles sem ganho de clareza. As provas de identificador e marcador já vivem em
`domain/authz_created`."""

import json
from dataclasses import dataclass

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
from harness_dast.domain.authz_config import normalize_field_name
from harness_dast.domain.authz_created import (
    created_identifier,
    created_read_exchange,
    parse_unique_json,
)
from harness_dast.domain.authz_findings import horizontal_finding
from harness_dast.domain.authz_flow_bindings import bindings_from_proven_body
from harness_dast.domain.authz_pair_inventory import inventory_ids, supports_inventory
from harness_dast.domain.authz_pair_marker import marker_fields
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_created_pair import CreatedPairTask
from harness_dast.domain.authz_plan_mass import MAX_MASS_REQUESTS
from harness_dast.domain.errors import ConfigError, TargetError
from harness_dast.domain.probe_exchange import ExchangeRecord


@dataclass(frozen=True)
class _Before:
    target: ExchangeRecord | None
    inventory: frozenset[str] = frozenset()


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
    markers = _make_marker(ctx, task, body, out)
    if not markers:
        return
    before = _prepare_before(ctx, task, body, out, markers)
    if before is None:
        return
    if ctx.settings.counter_checkpoint is not None and ctx.settings.builder is not None:
        ctx.settings.counter_checkpoint(ctx.settings.builder.next_unique_counter)
    ctx.shared_writes += 1
    out.writes += 1
    reply = ctx.sender.send(
        post, task.owner[0], body=body, with_body=True, tag="pair:", max_attempts=1
    )
    _check_created(ctx, task, out, reply, before, markers)


def _make_marker(
    ctx: CheckContext, task: CreatedPairTask, body: dict[str, JsonValue], out: CheckResult
) -> dict[str, str]:
    original = parse_json((task.post.body or "").encode())
    prior = original if isinstance(original, dict) else {}
    builder = ctx.settings.builder
    if builder is not None:
        bindings = bindings_from_proven_body(ctx.settings.flows, task.post.operation_id, original)
        candidates = marker_fields(
            ctx.settings.operations.get(task.post.operation_id),
            ctx.settings.operations.get(task.read.operation_id),
            frozenset(bindings.fields),
            ctx.settings.credential_fields,
        )
        marker_name = normalize_field_name(task.read.path.rsplit("/", 1)[-1].strip("{}"))
        for name, minimum, maximum in candidates:
            if name not in body or normalize_field_name(name) in {marker_name, "id"}:
                continue
            explicit = builder.body_rule_marker_eligible(task.post.operation_id, name)
            if explicit is False:
                continue
            if explicit is True:
                existing = body[name]
                if isinstance(existing, str) and existing != prior.get(name):
                    return {name: existing}
                continue
            try:
                value = builder.fresh_text(minimum, maximum)
                if value == prior.get(name):
                    value = builder.fresh_text(minimum, maximum)
            except ConfigError:
                continue
            if value != prior.get(name):
                body[name] = value
                return {name: value}
    out.not_tested.append(
        note(
            "horizontal",
            task.post,
            "new_marker_unavailable",
            "Não há campo textual independente que permita gerar e ler um marcador novo.",
        )
    )
    return {}


def _prepare_before(
    ctx: CheckContext,
    task: CreatedPairTask,
    body: dict[str, JsonValue],
    out: CheckResult,
    markers: dict[str, str],
) -> _Before | None:
    identifier = created_identifier(
        location=None,
        body=json.dumps(body).encode(),
        reader=task.read,
        base_url=ctx.settings.base_url,
    )
    if identifier is None:
        return _snapshot_collection(ctx, task, out, markers)
    target = _confirm_absent(ctx, task, identifier, out)
    return _Before(target) if target is not None else None


def _snapshot_collection(
    ctx: CheckContext, task: CreatedPairTask, out: CheckResult, markers: dict[str, str]
) -> _Before | None:
    collection = task.collection
    operation = ctx.settings.operations.get(collection.operation_id) if collection else None
    if collection is None or not supports_inventory(operation, task.read, frozenset(markers)):
        out.not_tested.append(
            note(
                "horizontal",
                task.post,
                "new_identifier_unavailable",
                "Sem identificador antecipado nem coleção provada sem parâmetros de consulta.",
            )
        )
        return None
    found: set[str] = set()
    for account in (task.owner[0], task.actor[0]):
        reply = ctx.sender.send(collection, account, tag="pair:", max_attempts=1)
        ids = (
            inventory_ids(reply.body, task.read, ctx.settings.base_url, markers)
            if _successful(ctx, reply)
            else None
        )
        if reply.problem is not None or ids is None:
            out.not_tested.append(
                note(
                    "horizontal",
                    collection,
                    "inventory_unavailable",
                    "A coleção não retornou inventário JSON válido para as duas contas.",
                )
            )
            return None
        found.update(ids)
    return _Before(None, frozenset(found))


def _confirm_absent(
    ctx: CheckContext, task: CreatedPairTask, identifier: str, out: CheckResult
) -> ExchangeRecord | None:
    target = created_read_exchange(task.read, identifier)
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
    expected: _Before,
    markers: dict[str, str],
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
    if (
        (expected.target is not None and target.target != expected.target.target)
        or identifier in expected.inventory
        or target.target.split("?", 1)[0] in task.existing_targets
    ):
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
    markers: dict[str, str],
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
    observed = _owner_object(ctx, task, target, out, owner.body)
    if observed is None:
        return
    if not any(
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
    out.remember_effect(
        task.post.operation_id, task.read.operation_id, task.owner[0], tuple(markers)
    )
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


def _owner_object(
    ctx: CheckContext, task: CreatedPairTask, target: ExchangeRecord, out: CheckResult, body: bytes
) -> dict[str, JsonValue] | None:
    observed = parse_unique_json(body)
    if observed is None:
        out.not_tested.append(
            note(
                "horizontal", target, "created_read_ambiguous", "Leitura JSON inválida ou ambígua."
            )
        )
        return None
    array = isinstance(observed, list)
    if isinstance(observed, list):
        if len(observed) != 1 or not isinstance(observed[0], dict):
            out.not_tested.append(
                note(
                    "horizontal",
                    target,
                    "created_read_ambiguous",
                    "A leitura da dona não retornou exatamente um objeto identificável.",
                )
            )
            return None
        observed = observed[0]
    if isinstance(observed, dict):
        marker = normalize_field_name(task.read.path.rsplit("/", 1)[-1].strip("{}"))
        has_identity = any(normalize_field_name(name) in {marker, "id"} for name in observed)
        found = created_identifier(
            location=None,
            body=json.dumps(observed).encode(),
            reader=task.read,
            base_url=ctx.settings.base_url,
        )
        if (array or has_identity) and (found is None or target.target.rsplit("/", 1)[-1] != found):
            out.not_tested.append(
                note(
                    "horizontal",
                    target,
                    "created_read_ambiguous",
                    "O objeto lido pela dona não confirmou o identificador da criação.",
                )
            )
            return None
    if not isinstance(observed, dict):
        out.not_tested.append(
            note(
                "horizontal",
                target,
                "new_marker_unconfirmed",
                "A leitura da dona não confirmou o marcador novo enviado na criação.",
            )
        )
        return None
    return observed
