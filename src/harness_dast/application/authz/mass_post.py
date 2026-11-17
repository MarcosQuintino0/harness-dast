"""Atribuição em massa num `POST` que cria recurso (ADR 0040).

Cada candidato é um `POST` com o corpo do `probe` mais o campo. Não há valor anterior a
restaurar e `DELETE` é proibido: cada `POST` aceito deixa UM recurso criado no ambiente de
teste, e quem limpa é o `hdast cleanup` ou o reset do ambiente (a contagem vai para `created`
e para o relatório). O efeito é conferido na leitura do recurso criado (`authz_created_read`)
ou, sem ela, na resposta do próprio `POST`.
"""

from harness_dast.application.authz.created_read import CreatedRead, read_created
from harness_dast.application.authz.mass_common import choose_injection
from harness_dast.application.authz.sender import (
    CheckContext,
    CheckResult,
    Reply,
    inconclusive,
    note,
    problem_note,
)
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.authz.candidates import Candidate, Injection
from harness_dast.domain.authz.compare import injected_effect, is_success_status
from harness_dast.domain.authz.findings import mass_assignment_finding
from harness_dast.domain.authz.plan_mass import MassTask
from harness_dast.domain.authz.result import AuthzFinding, AuthzNotTested
from harness_dast.domain.probe_exchange import ExchangeRecord

CONFLICT_STATUS = 409


def run_post_candidate(
    ctx: CheckContext,
    task: MassTask,
    original: dict[str, JsonValue],
    candidate: Candidate,
    out: CheckResult,
) -> bool:
    """Testa um campo num `POST`; devolve `False` quando não adianta tentar os demais.

    Não adianta continuar após conflito de unicidade (`409`), escopo recusado ou efeito
    inobservável: cada nova tentativa só criaria mais recursos à toa.
    """
    exchange = task.exchange
    chosen = choose_injection(exchange, original, candidate, None)
    if not isinstance(chosen, Injection):
        out.not_tested.append(chosen)
        return True
    out.writes += 1
    ctx.shared_writes += 1
    reply = ctx.sender.send(
        exchange,
        exchange.account,
        body={**original, chosen.name: chosen.value},
        with_body=True,
        max_attempts=1,
    )
    if reply.problem is not None:
        out.writes -= int(reply.problem == "mutation_pending")
        ctx.shared_writes -= int(reply.problem == "mutation_pending")
        out.not_tested.append(problem_note("mass_assignment", exchange, reply))
        return False
    if reply.status is None or reply.status >= 500:
        _unknown_post(ctx, exchange, reply, out)
        return True
    if reply.status == CONFLICT_STATUS:
        out.not_tested.append(_conflict_note(task))
        return False
    if reply.status in (401, 429):
        out.not_tested.append(inconclusive("mass_assignment", exchange, reply))
        return False
    out.tested += 1
    if not is_success_status(reply.status):
        return True
    out.created += 1
    seen = read_created(ctx, task, reply)
    if seen.via is None:
        out.not_tested.append(_unobservable_note(task, chosen.name))
        return False
    changed, _ = injected_effect(None, seen.body, chosen.name, chosen.value)
    if changed:
        out.findings.append(_finding(ctx, task, candidate, chosen, (changed, reply.status, seen)))
    elif task.candidate_readers:
        out.not_tested.append(_unobservable_note(task, chosen.name))
    return True


def _unknown_post(
    ctx: CheckContext, exchange: ExchangeRecord, reply: Reply, out: CheckResult
) -> None:
    if ctx.settings.mutation_journal is not None:
        out.not_tested.append(
            note(
                "mass_assignment",
                exchange,
                "mutation_pending",
                "Criação com efeito desconhecido; reconcilie o estado.",
            )
        )
    out.not_tested.append(inconclusive("mass_assignment", exchange, reply))


def _finding(
    ctx: CheckContext,
    task: MassTask,
    candidate: Candidate,
    chosen: Injection,
    seen: tuple[tuple[str, ...], int, CreatedRead],
) -> AuthzFinding:
    changed, status, read = seen
    exchange = task.exchange
    return mass_assignment_finding(
        product=ctx.settings.product,
        operation_id=exchange.operation_id,
        method=exchange.method,
        path_template=exchange.path,
        actor=(exchange.account, ctx.settings.roles.get(exchange.account)),
        sent_field=chosen.name,
        changed=changed,
        status=status,
        restored=None,
        source=candidate.source,
        kind=candidate.kind,
        observed_in=read.via or "post_response",
    )


def _conflict_note(task: MassTask) -> AuthzNotTested:
    return note(
        "mass_assignment",
        task.exchange,
        "create_conflict",
        "O servidor recusou o cadastro com conflito (409), provavelmente por um valor único do "
        "corpo do probe (e-mail, CPF...) já usado. A verificação não gera valores novos: "
        "declare o campo único em data-rules.yml para o probe gerar um valor por execução.",
    )


def _unobservable_note(task: MassTask, field_name: str) -> AuthzNotTested:
    return note(
        "mass_assignment",
        task.exchange,
        "effect_unobservable",
        f"O POST aceitou o campo '{field_name}', mas o efeito não foi confirmado. "
        "Um recurso foi criado e pode ficar no "
        "ambiente de teste (use `hdast cleanup` ou o reset do ambiente).",
    )
