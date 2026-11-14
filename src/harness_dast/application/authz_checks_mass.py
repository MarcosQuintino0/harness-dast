"""Verificação de atribuição em massa e a restauração do que ela altera.

Esta é a única verificação que ESCREVE no alvo: envia um `PUT` ou `PATCH` com um campo extra
(declarado ou derivado do OpenAPI, ADR 0040) e confere, na leitura seguinte, se o valor
injetado pegou. Quando pegou, tenta devolver o valor anterior e confere. Se uma parada (janela,
prazo, ZAP, alvo sem resposta) vier depois do envio, a restauração ainda é tentada pelo mesmo
caminho guardado; se não houver como confirmá-la, o aviso `possible_unrestored_change` vai para
`not_tested`. Nada disso é engolido: a parada volta a ser levantada para o laço. O `POST` que
cria recurso tem fluxo próprio (`authz_mass_post`: nada a restaurar). Nunca `DELETE`.
"""

from dataclasses import dataclass

from harness_dast.application.authz_mass_common import (
    as_object,
    choose_injection,
    current_value,
    no_body_note,
)
from harness_dast.application.authz_mass_post import run_post_candidate
from harness_dast.application.authz_sender import (
    INTERRUPTIONS,
    CheckContext,
    CheckResult,
    Reply,
    inconclusive,
    note,
    problem_note,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_candidates import Candidate, Injection
from harness_dast.domain.authz_compare import (
    holds_value,
    injected_effect,
    is_success_status,
    parse_json,
)
from harness_dast.domain.authz_findings import mass_assignment_finding
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_mass import MAX_MASS_REQUESTS, MassTask
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord


@dataclass
class _Pending:
    """Estado de um `PUT` de atribuição em massa que ainda pode ter deixado alteração."""

    attempted: bool = False
    known: bool = False
    previous: JsonValue = None


def run_mass(ctx: CheckContext, plan: Planned[MassTask]) -> CheckResult:
    """Envia cada campo candidato em cada operação de escrita planejada, um por pedido."""
    out = ctx.begin(
        "mass_assignment",
        CheckResult(
            not_tested=list(plan.not_tested),
            candidates=sum(len(task.candidates) for task in plan.tasks),
        ),
    )
    for task in plan.tasks:
        _mass_task(ctx, task, out)
    return out


def _mass_task(ctx: CheckContext, task: MassTask, out: CheckResult) -> None:
    original = as_object(task.exchange.body)
    if original is None:
        out.not_tested.append(no_body_note(task.exchange))
        return
    for candidate in task.candidates:
        if out.writes >= MAX_MASS_REQUESTS:
            out.not_tested.append(_budget_note(task))
            return
        if task.created:
            if not run_post_candidate(ctx, task, original, candidate, out):
                return
        else:
            _mass_one(ctx, task, original, candidate, out)


def _budget_note(task: MassTask) -> AuthzNotTested:
    return note(
        "mass_assignment",
        task.exchange,
        "budget_exhausted",
        f"O teto de {MAX_MASS_REQUESTS} pedidos de escrita por execução foi atingido; os "
        "campos restantes desta operação ficaram sem teste.",
    )


def _mass_one(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    candidate: Candidate,
    out: CheckResult,
) -> None:
    exchange = task.exchange
    if candidate.source == "declared":
        # O valor declarado não depende do estado: um valor repetido é recusado sem ler.
        chosen = choose_injection(exchange, original, candidate, None)
        before = _read(ctx, task) if isinstance(chosen, Injection) else None
    else:
        before = _read(ctx, task)
        chosen = choose_injection(
            exchange, original, candidate, current_value(before, candidate.name)
        )
    if not isinstance(chosen, Injection):
        out.not_tested.append(chosen)
        return
    pending = _Pending()
    try:
        _mass_apply(ctx, task, original, (candidate, chosen), before, out, pending)
    except INTERRUPTIONS:
        _after_interruption(ctx, task, original, chosen, before, pending, out)
        raise


def _mass_apply(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    chosen: tuple[Candidate, Injection],
    before: JsonValue | None,
    out: CheckResult,
    pending: _Pending,
) -> None:
    candidate, extra = chosen
    exchange = task.exchange
    pending.attempted = True
    out.writes += 1
    put = ctx.sender.send(
        exchange, exchange.account, body={**original, extra.name: extra.value}, with_body=True
    )
    if put.problem is not None:
        pending.attempted = False
        out.not_tested.append(problem_note("mass_assignment", exchange, put))
        return
    if put.status is None or put.status >= 500:
        out.not_tested.append(inconclusive("mass_assignment", exchange, put))
        return
    out.tested += 1
    if not is_success_status(put.status):
        pending.attempted = False
        return
    after = _read(ctx, task, fallback=put)
    changed, previous = injected_effect(before, after, extra.name, extra.value)
    if not changed:
        pending.attempted = False
        return
    pending.previous, pending.known = previous, True
    out.writes += 1
    restored = _restore(ctx, task, original, extra, changed, previous)
    pending.attempted = False
    if restored is not True:
        out.not_tested.append(_unrestored_note(exchange, extra.name, "restore_failed"))
    role = ctx.settings.roles.get(exchange.account)
    out.findings.append(
        mass_assignment_finding(
            product=ctx.settings.product,
            operation_id=exchange.operation_id,
            method=exchange.method,
            path_template=exchange.path,
            actor=(exchange.account, role),
            sent_field=extra.name,
            changed=changed,
            status=put.status,
            restored=restored,
            source=candidate.source,
            kind=candidate.kind,
        )
    )


def _after_interruption(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    extra: Injection,
    before: JsonValue | None,
    pending: _Pending,
    out: CheckResult,
) -> None:
    """Parada depois do `PUT`: tenta desfazer; se não der, avisa em `not_tested`.

    A restauração passa pelo mesmo caminho guardado: com a janela fechada, o prazo vencido
    ou a trava acionada nada é enviado e só o aviso fica registrado.
    """
    if not pending.attempted:
        return
    previous = pending.previous if pending.known else _previous_value(before, extra.name)
    if not _try_restore(ctx, task, original, extra, previous):
        out.not_tested.append(_unrestored_note(task.exchange, extra.name, "interrupted"))


def _try_restore(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    extra: Injection,
    previous: JsonValue,
) -> bool:
    if previous is None or isinstance(previous, dict | list):
        return False
    exchange = task.exchange
    try:
        reply = ctx.sender.send(
            exchange, exchange.account, body={**original, extra.name: previous}, with_body=True
        )
    except INTERRUPTIONS:
        return False
    return reply.problem is None and is_success_status(reply.status)


def _unrestored_note(exchange: ExchangeRecord, field_name: str, cause: str) -> AuthzNotTested:
    why = (
        "a execução parou depois do PUT e a restauração não pôde ser feita ou confirmada"
        if cause == "interrupted"
        else "a restauração não foi confirmada"
    )
    return note(
        "mass_assignment",
        exchange,
        "possible_unrestored_change",
        f"Possível alteração não desfeita na conta '{exchange.account}', operação "
        f"'{exchange.operation_id}': o campo extra '{field_name}' foi enviado e {why}. "
        "Confira o estado da conta e restaure por fora (reset do ambiente ou `cleanup`).",
    )


def _read(ctx: CheckContext, task: MassTask, fallback: Reply | None = None) -> JsonValue | None:
    """Corpo JSON da leitura seguinte (um GET provado pelo `probe`) ou da própria resposta."""
    if task.read is None:
        return parse_json(fallback.body) if fallback is not None else None
    reply = ctx.sender.send(task.read, task.read.account)
    return parse_json(reply.body) if is_success_status(reply.status) else None


def _restore(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    extra: Injection,
    changed: tuple[str, ...],
    previous: JsonValue,
) -> bool | None:
    """Tenta devolver o valor anterior; `None` se não havia valor escalar para devolver."""
    if previous is None or isinstance(previous, dict | list):
        return None
    exchange = task.exchange
    ctx.sender.send(
        exchange, exchange.account, body={**original, extra.name: previous}, with_body=True
    )
    again = _read(ctx, task)
    return again is not None and not holds_value(again, changed, extra.value)


def _previous_value(before: JsonValue | None, name: str) -> JsonValue:
    """Valor da leitura anterior com o mesmo nome do campo enviado (`None` se não há)."""
    return before.get(name) if isinstance(before, dict) else None
