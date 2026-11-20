"""Verificação CORS sobre leituras provadas, pelo emissor protegido do authz."""

import hashlib

from harness_dast.application.authz.sender import (
    CheckContext,
    CheckResult,
    inconclusive,
    problem_note,
)
from harness_dast.domain.authz.compare import is_success_status
from harness_dast.domain.authz.plan import Planned
from harness_dast.domain.cors import CorsPolicy, classify_cors, cors_finding
from harness_dast.domain.probe_exchange import ExchangeRecord


def run_cors(ctx: CheckContext, plan: Planned[ExchangeRecord]) -> CheckResult:
    """Envia uma origem inexistente por GET e agrega uma ocorrência por classe."""
    out = ctx.begin(
        "cors", CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
    )
    origin = "https://" + hashlib.sha256(ctx.settings.run_id.encode()).hexdigest()[:24] + ".invalid"
    seen: set[CorsPolicy] = set()
    for exchange in plan.tasks:
        reply = ctx.sender.send(
            exchange, exchange.account, tag="cors:", origin=origin, max_attempts=1
        )
        if reply.problem is not None:
            out.not_tested.append(problem_note("cors", exchange, reply))
            continue
        if not is_success_status(reply.status):
            out.not_tested.append(inconclusive("cors", exchange, reply))
            continue
        out.tested += 1
        policy = classify_cors(origin, reply.cors_allow_origin, reply.cors_allow_credentials)
        if policy is not None and policy not in seen and reply.status is not None:
            seen.add(policy)
            out.findings.append(
                cors_finding(
                    ctx.settings.product,
                    exchange,
                    ctx.settings.roles.get(exchange.account),
                    reply.status,
                    policy,
                )
            )
    return out
