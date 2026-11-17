"""Verificações de acesso: pedido sem login e token adulterado (ADR 0039, 0098). Só leem (`GET`).

`run_anonymous` repete o `GET` da conta dona sem nenhuma credencial; `run_tampered` o repete com o
token da conta dona estragado de propósito (nunca válido, nunca de outra conta) e sem cookie. O
veredito de cada pedido é do domínio (`judge_replay`, `conclude_variants`); aqui só se envia,
se compara com a linha de base e se anota o que não pôde ser testado. Todo pedido passa pelo
`ReplaySender` (cerca, `deny_paths`, taxa, janela, prazo, trava e auditoria). O valor de um token
(original ou adulterado) nunca é gravado nem aparece em mensagem.
"""

from harness_dast.application.account_session import AuthCredential
from harness_dast.application.authz.sender import (
    CheckContext,
    CheckResult,
    Reply,
    inconclusive,
    note,
    problem_note,
    usable_baseline,
)
from harness_dast.application.authz.tamper import TamperedSession
from harness_dast.domain.authz.anonymous import accepted_variants, conclude_variants
from harness_dast.domain.authz.compare import (
    Verdict,
    bodies_equivalent,
    is_success_status,
    judge_replay,
)
from harness_dast.domain.authz.findings_access import anonymous_finding, tampered_finding
from harness_dast.domain.authz.jwt_forge import (
    MAX_PROOF_REQUESTS_PER_OPERATION,
    MAX_WEAK_KEY_OPERATIONS,
    WeakKey,
    find_weak_key,
    forge_with_weak_key,
)
from harness_dast.domain.authz.plan import Planned
from harness_dast.domain.authz.result import AuthzNotTested
from harness_dast.domain.authz.token import TamperedToken, TamperVariant, build_tampered_tokens
from harness_dast.domain.errors import PreflightError
from harness_dast.domain.probe_exchange import ExchangeRecord

_SERVER_ERROR = 500


def _verdict(ctx: CheckContext, base: Reply, reply: Reply) -> Verdict:
    same = bodies_equivalent(base.body, reply.body, ctx.volatile)
    return judge_replay(base.status, reply.status, equivalent=same)


def run_anonymous(ctx: CheckContext, plan: Planned[ExchangeRecord]) -> CheckResult:
    """Repete cada `GET` sem credencial: `2xx` com o mesmo conteúdo é falta de autenticação."""
    out = ctx.begin(
        "anonymous_access",
        CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks)),
    )
    for exchange in plan.tasks:
        base = usable_baseline("anonymous_access", exchange, ctx.sender, out)
        if base is None or base.status is None:
            continue
        reply = ctx.sender.anonymous(exchange)
        if reply.problem is not None:
            out.not_tested.append(problem_note("anonymous_access", exchange, reply))
            continue
        verdict = _verdict(ctx, base, reply)
        if verdict == "error":
            out.not_tested.append(inconclusive("anonymous_access", exchange, reply))
            continue
        out.tested += 1
        if verdict == "allowed_equivalent" and reply.status is not None:
            out.findings.append(
                anonymous_finding(
                    product=ctx.settings.product,
                    operation_id=exchange.operation_id,
                    method=exchange.method,
                    path_template=exchange.path,
                    actor=(exchange.account, ctx.settings.roles.get(exchange.account)),
                    operation=ctx.settings.operations.get(exchange.operation_id),
                    statuses=(base.status, reply.status),
                )
            )
    return out


def _closed_to_anonymous(ctx: CheckContext, exchange: ExchangeRecord, out: CheckResult) -> bool:
    """Confirma que o pedido sem credencial foi recusado; anota o motivo se não foi.

    O servidor que responde `2xx` sem credencial ignora o token: adulterá-lo não diz nada.
    Reaproveita a resposta de `anonymous_access` (cache do emissor); se essa verificação não
    rodou, o pedido sem credencial é enviado agora (um só).
    """
    anon = ctx.sender.anonymous(exchange)
    if anon.problem is not None:
        out.not_tested.append(problem_note("tampered_token", exchange, anon))
    elif is_success_status(anon.status):
        out.not_tested.append(
            note(
                "tampered_token",
                exchange,
                "anonymous_already_open",
                "A operação responde sem credencial: o servidor ignora o token, então adulterá-lo "
                "não diz nada. Veja o resultado de anonymous_access.",
            )
        )
    elif anon.status is None or anon.status >= _SERVER_ERROR:
        out.not_tested.append(inconclusive("tampered_token", exchange, anon))
    else:
        return True
    return False


def _prepare(
    ctx: CheckContext, exchange: ExchangeRecord
) -> tuple[AuthCredential, tuple[TamperedToken, ...]] | AuthzNotTested:
    """Credencial da conta dona e as variantes adulteradas, ou a anotação do que impede."""
    try:
        credential = ctx.settings.sessions.get(exchange.account).credential()
    except PreflightError:
        return note(
            "tampered_token",
            exchange,
            "account_unavailable",
            "A conta dona não conseguiu abrir sessão (login recusado).",
        )
    if credential is None:
        return note(
            "tampered_token",
            exchange,
            "no_credential",
            "A conta dona não tem credencial (token ou chave) para adulterar.",
        )
    variants = build_tampered_tokens(credential.value, allow_jwt=credential.kind == "token")
    if not variants:
        return note(
            "tampered_token",
            exchange,
            "token_too_short",
            "O token não tem texto suficiente para ser embaralhado (menos de 2 caracteres ou "
            "com espaço); nada foi enviado.",
        )
    return credential, variants


def _send_variants(
    ctx: CheckContext,
    exchange: ExchangeRecord,
    base: Reply,
    prepared: tuple[AuthCredential, tuple[TamperedToken, ...]],
) -> tuple[list[tuple[TamperVariant, Verdict]], dict[TamperVariant, int], Reply | None]:
    """Envia cada variante; devolve vereditos, códigos e o pedido recusado pelo escopo, se houve."""
    credential, variants = prepared
    results: list[tuple[TamperVariant, Verdict]] = []
    statuses: dict[TamperVariant, int] = {}
    for item in variants:
        session = TamperedSession(credential, item.value, ctx.settings.vault)
        reply = ctx.sender.tampered(exchange, session)
        if reply.problem is not None:
            return results, statuses, reply
        results.append((item.variant, _verdict(ctx, base, reply)))
        if reply.status is not None:
            statuses[item.variant] = reply.status
    return results, statuses, None


class _WeakKeyBudget:
    """Estado de UMA execução do teste de chave fraca: operações restantes e chave por conta."""

    def __init__(self, extra_candidates: tuple[str, ...]) -> None:
        self.remaining = MAX_WEAK_KEY_OPERATIONS
        self._extra = extra_candidates
        self._keys: dict[str, WeakKey | None] = {}

    def key_for(self, account: str, credential: AuthCredential) -> WeakKey | None:
        """Quebra a chave offline uma vez por conta; token que não é `Bearer` nunca é tentado."""
        if account not in self._keys:
            found = (
                find_weak_key(credential.value, self._extra) if credential.kind == "token" else None
            )
            self._keys[account] = found
        return self._keys[account]


def _send_weak_key(
    ctx: CheckContext,
    exchange: ExchangeRecord,
    base: Reply,
    credential: AuthCredential,
    weak: WeakKey,
) -> tuple[list[tuple[TamperVariant, Verdict]], dict[TamperVariant, int], Reply | None]:
    """Até dois pedidos de prova: token re-assinado e, se aceito, o mesmo com `exp` vencido."""
    results: list[tuple[TamperVariant, Verdict]] = []
    statuses: dict[TamperVariant, int] = {}
    forged = forge_with_weak_key(credential.value, weak)
    if forged is None:
        return results, statuses, None
    ctx.settings.vault.register(weak.key)
    for item in forged[:MAX_PROOF_REQUESTS_PER_OPERATION]:
        reply = ctx.sender.tampered(
            exchange, TamperedSession(credential, item.value, ctx.settings.vault)
        )
        if reply.problem is not None:
            return results, statuses, reply
        verdict = _verdict(ctx, base, reply)
        results.append((item.variant, verdict))
        if reply.status is not None:
            statuses[item.variant] = reply.status
        if verdict != "allowed_equivalent":
            break
    return results, statuses, None


def _tamper_operation(
    ctx: CheckContext,
    exchange: ExchangeRecord,
    out: CheckResult,
    budget: _WeakKeyBudget,
) -> None:
    base = usable_baseline("tampered_token", exchange, ctx.sender, out)
    if base is None or base.status is None or not _closed_to_anonymous(ctx, exchange, out):
        return
    prepared = _prepare(ctx, exchange)
    if isinstance(prepared, AuthzNotTested):
        out.not_tested.append(prepared)
        return
    results, statuses, refused = _send_variants(ctx, exchange, base, prepared)
    weak = budget.key_for(exchange.account, prepared[0]) if refused is None else None
    if weak is not None and budget.remaining > 0 and not accepted_variants(results):
        budget.remaining -= 1
        more, more_statuses, refused = _send_weak_key(ctx, exchange, base, prepared[0], weak)
        results += more
        statuses.update(more_statuses)
    if refused is not None:
        out.not_tested.append(problem_note("tampered_token", exchange, refused))
        return
    conclusion = conclude_variants(results)
    if conclusion == "inconclusive":
        out.not_tested.append(
            note(
                "tampered_token",
                exchange,
                "inconclusive",
                "Alguma variante ficou sem resposta ou deu erro do servidor; não conta "
                "como seguro.",
            )
        )
        return
    out.tested += 1
    accepted = accepted_variants(results)
    if conclusion == "finding" and accepted:
        out.findings.append(
            tampered_finding(
                product=ctx.settings.product,
                operation_id=exchange.operation_id,
                method=exchange.method,
                path_template=exchange.path,
                actor=(exchange.account, ctx.settings.roles.get(exchange.account)),
                variants=accepted,
                statuses=(base.status, statuses[accepted[0]]),
            )
        )


def run_tampered(ctx: CheckContext, plan: Planned[ExchangeRecord]) -> CheckResult:
    """Repete cada `GET` com o token adulterado: aceitar é não conferir o token (assinatura).

    Se nenhuma variante comum foi aceita e o token é um JWT HMAC com chave da lista fraca
    (achada offline), a operação recebe até dois pedidos de prova (ADR 0098), dentro do teto
    de `MAX_WEAK_KEY_OPERATIONS` operações por execução.
    """
    out = ctx.begin(
        "tampered_token",
        CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks)),
    )
    budget = _WeakKeyBudget((ctx.settings.product,))
    for exchange in plan.tasks:
        _tamper_operation(ctx, exchange, out, budget)
    return out
