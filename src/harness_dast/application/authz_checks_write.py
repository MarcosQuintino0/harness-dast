"""Verificação `horizontal_write`: a conta B tenta ALTERAR o recurso da conta A (ADR 0042).

Só roda com `authz.allow_writes` (quem decide é o plano). Para cada `PUT` ou `PATCH` provado, com
identificador de objeto: a conta dona lê o recurso (antes), o domínio escolhe UM campo e um valor
de teste que difere do atual (`authz_marker`), a conta par envia o mesmo pedido com só esse campo
trocado, e a conta dona lê de novo. Se o campo passou a valer o marcador, houve alteração por
quem não era o dono: achado alto. Depois a conta dona restaura o valor anterior (restaurador
comum, `authz_restore`). `401`, `403` e `404` na escrita são negação (esperado); `400`, `409`,
`422`, `5xx` e falta de resposta não concluem; `2xx` sem efeito visível NUNCA é "seguro". Nunca
`DELETE`; nunca mais de um campo nem de uma conta par; nada é gravado com o valor do campo.
"""

from typing import Final

from harness_dast.application.authz_mass_common import as_object
from harness_dast.application.authz_restore import (
    Pending,
    after_interruption,
    read_body,
    restore,
    try_restore,
    unrestored_note,
)
from harness_dast.application.authz_sender import (
    INTERRUPTIONS,
    CheckContext,
    CheckResult,
    inconclusive,
    note,
    problem_note,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz_compare import holds_value, is_success_status, parse_json
from harness_dast.domain.authz_findings_write import horizontal_write_finding
from harness_dast.domain.authz_marker import Marker, choose_marker
from harness_dast.domain.authz_plan import Planned
from harness_dast.domain.authz_plan_write import WriteTask

CHECK: Final = "horizontal_write"
DENIED_WRITE: Final = frozenset({401, 403, 404})
"""Na escrita o `404` também é negação: o servidor "esconde" o recurso de quem não é o dono."""


def run_horizontal_write(ctx: CheckContext, plan: Planned[WriteTask]) -> CheckResult:
    """Tenta escrever, com uma conta par, no recurso de cada candidato planejado."""
    out = ctx.begin(
        CHECK, CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
    )
    for task in plan.tasks:
        _write_task(ctx, task, out)
    return out


def _write_task(ctx: CheckContext, task: WriteTask, out: CheckResult) -> None:
    exchange = task.exchange
    original = as_object(exchange.body)
    if original is None:
        out.not_tested.append(
            note(
                CHECK,
                exchange,
                "no_json_body",
                "O probe não guardou um corpo JSON (objeto) para esta operação.",
            )
        )
        return
    before = _read_before(ctx, task, out)
    if before is None:
        return
    marker = choose_marker(original, before, task.properties)
    if marker is None:
        out.not_tested.append(
            note(
                CHECK,
                exchange,
                "no_detectable_field",
                "Nenhum campo de primeiro nível (texto ou inteiro, fora de segredo, "
                "identificador, privilégio, saldo, preço, estado, dono e auditoria) aparece "
                "igual no corpo do probe e na leitura do recurso; não há como confirmar a "
                "escrita.",
            )
        )
        return
    pending = Pending()
    try:
        _write_apply(ctx, task, original, marker, out, pending)
    except INTERRUPTIONS:
        after_interruption(
            ctx,
            out,
            pending,
            (CHECK, exchange, original),
            marker.field,
            marker.previous,
            (_what(task, marker), "da escrita da outra conta"),
        )
        raise


def _what(task: WriteTask, marker: Marker) -> str:
    return f"a conta '{task.actor[0]}' enviou a escrita no campo '{marker.field}'"


def _read_before(ctx: CheckContext, task: WriteTask, out: CheckResult) -> JsonValue | None:
    """Leitura da conta dona antes da escrita (objeto JSON), ou `None` com a anotação em `out`."""
    exchange = task.exchange
    reply = ctx.sender.send(task.read, task.read.account)
    if reply.problem is not None:
        out.not_tested.append(problem_note(CHECK, exchange, reply))
        return None
    body = parse_json(reply.body) if is_success_status(reply.status) else None
    if not isinstance(body, dict):
        out.not_tested.append(
            note(
                CHECK,
                exchange,
                "baseline_failed",
                "A conta dona não leu o recurso agora (status "
                f"{reply.status}) ou a resposta não é um objeto JSON; sem a leitura antes "
                "não há como confirmar a escrita.",
            )
        )
        return None
    return body


def _write_apply(
    ctx: CheckContext,
    task: WriteTask,
    original: dict[str, JsonValue],
    marker: Marker,
    out: CheckResult,
    pending: Pending,
) -> None:
    exchange = task.exchange
    pending.attempted = True
    out.writes += 1
    reply = ctx.sender.send(
        exchange,
        task.actor[0],
        body={**original, marker.field: marker.value},
        with_body=True,
        tag="write:",
    )
    if reply.problem is not None:
        pending.attempted = False
        out.not_tested.append(problem_note(CHECK, exchange, reply))
    elif reply.status in DENIED_WRITE:
        pending.attempted = False
        out.tested += 1
    elif not is_success_status(reply.status) or reply.status is None:
        pending.attempted = False
        out.not_tested.append(inconclusive(CHECK, exchange, reply))
    else:
        _confirm(ctx, task, original, marker, (out, pending), reply.status)


def _confirm(
    ctx: CheckContext,
    task: WriteTask,
    original: dict[str, JsonValue],
    marker: Marker,
    state: tuple[CheckResult, Pending],
    status: int,
) -> None:
    """A escrita da conta par teve 2xx: a conta dona relê para ver se o campo mudou."""
    out, pending = state
    exchange = task.exchange
    after = read_body(ctx, task.read)
    if after is None:
        _unconfirmed(ctx, task, original, marker, out)
    elif not holds_value(after, (marker.field,), marker.value):
        out.not_tested.append(
            note(
                CHECK,
                exchange,
                "accepted_without_visible_effect",
                f"A conta '{task.actor[0]}' recebeu {status} ao escrever no recurso da conta "
                f"'{task.owner[0]}', mas a leitura da conta dona não mostra a mudança no campo "
                f"'{marker.field}'. Não há prova de alteração (não é achado), mas também NÃO "
                "é seguro: o servidor aceitou a escrita de outra conta. Confira à mão.",
            )
        )
    else:
        out.tested += 1
        pending.previous, pending.known = marker.previous, True
        out.writes += 1
        restored = restore(
            ctx,
            exchange,
            task.read,
            original,
            (marker.field, marker.value),
            (marker.field,),
            marker.previous,
        )
        if restored is not True:
            out.not_tested.append(
                unrestored_note(
                    CHECK, exchange, _what(task, marker), "da escrita da outra conta", "restore"
                )
            )
        out.findings.append(
            horizontal_write_finding(
                product=ctx.settings.product,
                operation_id=exchange.operation_id,
                method=exchange.method,
                path_template=exchange.path,
                actor=task.actor,
                owner=task.owner,
                status=status,
                field=marker.field,
                restored=restored is True,
            )
        )
    pending.attempted = False


def _unconfirmed(
    ctx: CheckContext,
    task: WriteTask,
    original: dict[str, JsonValue],
    marker: Marker,
    out: CheckResult,
) -> None:
    """A escrita teve 2xx mas a leitura de conferência falhou: tenta restaurar e avisa."""
    exchange = task.exchange
    if not try_restore(ctx, exchange, original, marker.field, marker.previous):
        out.not_tested.append(
            unrestored_note(
                CHECK, exchange, _what(task, marker), "da escrita da outra conta", "restore"
            )
        )
        return
    out.not_tested.append(
        note(
            CHECK,
            exchange,
            "inconclusive",
            "A escrita da outra conta teve sucesso, mas a leitura de conferência falhou; "
            "o valor anterior foi reenviado pela conta dona. Não conta como seguro.",
        )
    )
