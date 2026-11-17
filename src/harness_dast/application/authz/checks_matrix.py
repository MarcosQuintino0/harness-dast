"""Verificação `access_matrix`: testa cada "não pode" da tabela quem pode o quê (ADR 0041).

O plano (`authz_matrix_plan`, puro) já decidiu o que enviar e o que fica sem teste; aqui só se
envia, UM pedido por célula proibida, com a primeira conta do papel (`operation_id`
`authz:matrix:<operação>`), pelo `ReplaySender` e portanto pela cerca. O veredito é do domínio:
401 e 403 passam, `2xx` falha, o resto é "não testado". Uma parada no meio (janela, prazo,
proxy, alvo sem resposta) não perde a tabela: as células ainda sem pedido saem `not_run`.
"""

from harness_dast.application.authz.sender import CheckContext, CheckResult, Reply, problem_note
from harness_dast.domain.authz.findings_matrix import matrix_finding
from harness_dast.domain.authz.matrix_cells import (
    MatrixTask,
    cell_from_reply,
    failed_by_probe_cell,
    not_tested_cell,
)
from harness_dast.domain.authz.matrix_plan import MatrixPlan, assemble_rows
from harness_dast.domain.authz.matrix_report import AccessMatrixReport, MatrixCell
from harness_dast.domain.authz.result import AuthzNotTested


def run_access_matrix(ctx: CheckContext, plan: MatrixPlan) -> CheckResult:
    """Testa as células proibidas e devolve a tabela com o resultado de cada uma."""
    out = ctx.begin(
        "access_matrix",
        CheckResult(not_tested=list(plan.notes), candidates=plan.candidates),
    )
    resolved: dict[tuple[int, int], MatrixCell] = {}
    try:
        for task in plan.proved:
            _record_failure(ctx, out, task, task.exchange.status, "probe")
            resolved[(task.row, task.col)] = failed_by_probe_cell(task)
            out.tested += 1
        for task in plan.sends:
            resolved[(task.row, task.col)] = _send(ctx, out, task)
    finally:
        out.matrix = AccessMatrixReport(roles=plan.roles, rows=assemble_rows(plan, resolved))
    return out


def _send(ctx: CheckContext, out: CheckResult, task: MatrixTask) -> MatrixCell:
    exchange = task.exchange
    reply = ctx.sender.send(exchange, task.actor, tag="matrix:")
    if reply.problem is not None:
        return _problem_cell(out, task, reply)
    cell = cell_from_reply(task, reply.status)
    if cell.result == "not_tested":
        out.not_tested.append(_cell_note(task, cell))
        return cell
    out.tested += 1
    if cell.result == "failed" and reply.status is not None:
        _record_failure(ctx, out, task, reply.status, "replay")
        if exchange.method == "POST":
            out.created += 1
    return cell


def _record_failure(
    ctx: CheckContext, out: CheckResult, task: MatrixTask, status: int, source: str
) -> None:
    out.findings.append(
        matrix_finding(product=ctx.settings.product, task=task, status=status, source=source)
    )


def _problem_cell(out: CheckResult, task: MatrixTask, reply: Reply) -> MatrixCell:
    """Pedido recusado pelo escopo (ou conta sem sessão): nada foi enviado, "não testado"."""
    base = problem_note("access_matrix", task.exchange, reply)
    out.not_tested.append(base.model_copy(update={"message": f"Papel {task.role}: {base.message}"}))
    return not_tested_cell(task.role, base.reason, base.message).model_copy(
        update={"account": task.actor}
    )


def _cell_note(task: MatrixTask, cell: MatrixCell) -> AuthzNotTested:
    exchange = task.exchange
    return AuthzNotTested(
        check="access_matrix",
        operation_id=exchange.operation_id,
        method=exchange.method,
        path=exchange.path,
        reason=cell.reason or "inconclusive",
        message=f"Papel {task.role}: {cell.message}",
    )
