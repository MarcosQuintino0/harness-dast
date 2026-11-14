"""Verificações de leitura do teste de autorização: horizontal, excessive_data e vertical.

Cada função recebe o `CheckContext` e o plano da verificação (calculado no domínio) e devolve
o `CheckResult`. A decisão do veredito é do domínio (`authz_compare`); aqui só se envia, se
compara com a linha de base e se registra o que não pôde ser testado. Nenhuma delas escreve
no alvo: repetem pedidos de leitura já provados pelo `probe`.
"""

from harness_dast.application.authz_sender import (
    CheckContext,
    CheckResult,
    Reply,
    inconclusive,
    note,
    problem_note,
    usable_baseline,
)
from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.authz_compare import (
    bodies_equivalent,
    has_empty_list,
    is_success_status,
    judge_replay,
    parse_json,
    unexpected_fields,
)
from harness_dast.domain.authz_findings import (
    excessive_data_finding,
    horizontal_finding,
    vertical_finding,
)
from harness_dast.domain.authz_plan import Planned, ReplayTask
from harness_dast.domain.authz_result import AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

DENIED_STATUSES = frozenset({401, 403})
"""No acesso vertical só 401 e 403 provam que o servidor negou; 400, 404 e 409 são ambíguos."""


def run_horizontal(ctx: CheckContext, plan: Planned[ReplayTask]) -> CheckResult:
    """Repete a leitura da conta dona com outra conta do mesmo papel (BOLA/IDOR)."""
    out = ctx.begin(
        "horizontal", CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
    )
    for task in plan.tasks:
        exchange = task.exchange
        base = usable_baseline("horizontal", exchange, ctx.sender, out)
        if base is None:
            continue
        replay = ctx.sender.send(exchange, task.actor[0])
        if replay.problem is not None:
            out.not_tested.append(problem_note("horizontal", exchange, replay))
            continue
        same = bodies_equivalent(base.body, replay.body, ctx.volatile)
        verdict = judge_replay(base.status, replay.status, equivalent=same)
        if verdict == "error":
            out.not_tested.append(inconclusive("horizontal", exchange, replay))
            continue
        out.tested += 1
        if verdict == "allowed_equivalent" and base.status is not None and replay.status:
            out.findings.append(
                horizontal_finding(
                    product=ctx.settings.product,
                    operation_id=exchange.operation_id,
                    method=exchange.method,
                    path_template=exchange.path,
                    actor=task.actor,
                    owner=task.owner,
                    statuses=(base.status, replay.status),
                )
            )
    return out


def run_excessive(ctx: CheckContext, plan: Planned[ExchangeRecord]) -> CheckResult:
    """Compara a resposta de sucesso com o esquema do OpenAPI e aponta campos a mais."""
    out = ctx.begin(
        "excessive_data",
        CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks)),
    )
    for exchange in plan.tasks:
        reply = ctx.sender.baseline(exchange)
        operation = ctx.settings.operations.get(exchange.operation_id)
        schema = _response_schema(operation, reply.status)
        body = parse_json(reply.body) if is_success_status(reply.status) else None
        if schema is None or body is None:
            out.not_tested.append(_no_schema_note(exchange, reply, schema is None))
            continue
        fields = unexpected_fields(schema, body)
        if not fields and has_empty_list(schema, body):
            out.not_tested.append(
                note(
                    "excessive_data",
                    exchange,
                    "no_sample_data",
                    "A resposta veio com lista vazia, sem item para comparar com o esquema; "
                    "não conta como seguro. Ajuste a paginação do pedido (por exemplo, "
                    "`page` e `size` em data-rules.yml) para o probe receber itens.",
                )
            )
            continue
        out.tested += 1
        if fields and reply.status is not None:
            role = ctx.settings.roles.get(exchange.account)
            out.findings.append(
                excessive_data_finding(
                    product=ctx.settings.product,
                    operation_id=exchange.operation_id,
                    method=exchange.method,
                    path_template=exchange.path,
                    actor=(exchange.account, role),
                    status=reply.status,
                    fields=fields,
                )
            )
    return out


def run_vertical(ctx: CheckContext, plan: Planned[ReplayTask]) -> CheckResult:
    """Repete a operação de papel maior com a conta de papel menor (BFLA)."""
    out = ctx.begin(
        "vertical", CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
    )
    for task in plan.tasks:
        exchange = task.exchange
        reply = ctx.sender.send(exchange, task.actor[0])
        if reply.problem is not None:
            out.not_tested.append(problem_note("vertical", exchange, reply))
        elif is_success_status(reply.status) and reply.status is not None:
            out.tested += 1
            out.findings.append(
                vertical_finding(
                    product=ctx.settings.product,
                    operation_id=exchange.operation_id,
                    method=exchange.method,
                    path_template=exchange.path,
                    actor=task.actor,
                    owner=task.owner,
                    statuses=(exchange.status, reply.status),
                )
            )
        elif reply.status in DENIED_STATUSES:
            out.tested += 1
        else:
            out.not_tested.append(inconclusive("vertical", exchange, reply))
    return out


def _no_schema_note(exchange: ExchangeRecord, reply: Reply, missing_schema: bool) -> AuthzNotTested:
    if missing_schema:
        return note(
            "excessive_data",
            exchange,
            "no_response_schema",
            "O OpenAPI não declara o esquema da resposta de sucesso desta operação.",
        )
    return note(
        "excessive_data",
        exchange,
        "no_json_response",
        f"A resposta (status {reply.status}) não é um JSON de sucesso para comparar.",
    )


def _response_schema(operation: Operation | None, status: int | None) -> Schema | None:
    if operation is None or status is None:
        return None
    exact = [r for r in operation.success_responses if r.status == str(status)]
    success = [r for r in operation.success_responses if r.status.startswith("2")]
    for response in (*exact, *success):
        if response.body_schema is not None:
            return response.body_schema
    return None
