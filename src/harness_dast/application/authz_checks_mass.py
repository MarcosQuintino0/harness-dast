"""Verificação de atribuição em massa e a restauração do que ela altera.

Esta verificação ESCREVE no alvo (a outra é `horizontal_write`): envia um `PUT` ou `PATCH` com um
campo extra (declarado ou derivado do OpenAPI, ADR 0040) e confere, na leitura seguinte, se o valor
injetado pegou. Quando pegou, tenta devolver o valor anterior e confere. Se uma parada (janela,
prazo, ZAP, alvo sem resposta) vier depois do envio, a restauração ainda é tentada pelo mesmo
caminho guardado; se não houver como confirmá-la, o aviso `possible_unrestored_change` vai para
`not_tested`. Nada disso é engolido: a parada volta a ser levantada para o laço. O `POST` que
cria recurso tem fluxo próprio (`authz_mass_post`: nada a restaurar). A restauração é a de
`authz_restore`, comum às duas verificações de escrita. Nunca `DELETE`.
"""

from harness_dast.application.authz_mass_common import (
    as_object,
    choose_injection,
    current_value,
    no_body_note,
)
from harness_dast.application.authz_mass_post import run_post_candidate
from harness_dast.application.authz_restore import (
    Pending,
    after_interruption,
    read_body,
    restore,
    unrestored_note,
)
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
    injected_effect,
    is_success_status,
    parse_json,
)
from harness_dast.domain.authz_findings import mass_assignment_finding
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_mass import MAX_MASS_REQUESTS, MassTask
from harness_dast.domain.authz_result import AuthzNotTested


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
        if ctx.shared_writes >= MAX_MASS_REQUESTS - (0 if task.created else 1):
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
    pending = Pending()
    try:
        _mass_apply(ctx, task, original, (candidate, chosen), before, out, pending)
    except INTERRUPTIONS:
        after_interruption(
            ctx,
            out,
            pending,
            ("mass_assignment", exchange, original),
            chosen.name,
            _previous_value(before, chosen.name),
            (_what(chosen.name), "do PUT"),
        )
        raise


def _mass_apply(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    chosen: tuple[Candidate, Injection],
    before: JsonValue | None,
    out: CheckResult,
    pending: Pending,
) -> None:
    candidate, extra = chosen
    exchange = task.exchange
    pending.attempted = True
    out.writes += 1
    ctx.shared_writes += 1
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
    ctx.shared_writes += 1
    restored = restore(
        ctx, exchange, task.read, original, (extra.name, extra.value), changed, previous
    )
    pending.attempted = False
    if restored is not True:
        out.not_tested.append(
            unrestored_note(
                "mass_assignment", exchange, _what(extra.name), "do PUT", "restore_failed"
            )
        )
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


def _what(field_name: str) -> str:
    return f"o campo extra '{field_name}' foi enviado"


def _read(ctx: CheckContext, task: MassTask, fallback: Reply | None = None) -> JsonValue | None:
    """Corpo JSON da leitura seguinte (um GET provado pelo `probe`) ou da própria resposta."""
    if task.read is None:
        return parse_json(fallback.body) if fallback is not None else None
    return read_body(ctx, task.read)


def _previous_value(before: JsonValue | None, name: str) -> JsonValue:
    """Valor da leitura anterior com o mesmo nome do campo enviado (`None` se não há)."""
    return before.get(name) if isinstance(before, dict) else None
