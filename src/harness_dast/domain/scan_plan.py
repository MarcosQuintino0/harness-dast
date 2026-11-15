"""Plano da varredura: o que vira varredura do ZAP e por que o resto não.

A CLI decide, nunca o ZAP (o spike do M0 mostrou que o ZAP não exclui por método e que o
varredor inventa caminhos). O plano usa só o que o `probe` da MESMA execução provou:

- só operações com `success` (e, por flag, outras classes de uma lista fechada);
- `ScopeGuard` sobre a URL concreta aprendida: fora do escopo ou em `deny_paths`, nunca;
- `DELETE`, nunca; o login (`auth.token_path`), nunca (centenas de senhas ruins bloqueariam a
  conta);
- cada requisição é varrida com a CONTA que a enviou no `probe` (o token certo por varredura);
- `PUT`/`PATCH` só sobre recurso criado nesta execução (a operação consome um valor de
  `flows.yml` cujo produtor teve sucesso) ou quando o perfil liga `scan.mutating_methods`;
- sem mensagem aprendida no ZAP, nada a varrer.

O ZAP não restringe método: a camada de rede (proxy de escopo, ADR 0017) é quem impõe o que o
varredor gera; este plano só decide o que SE PEDE. Este módulo é puro.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal
from urllib.parse import urlsplit

from harness_dast.domain.api_schema import ApiModel
from harness_dast.domain.audit import AuditEntry
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult
from harness_dast.domain.scan_config import EXTRA_OUTCOMES, ScanConfig
from harness_dast.domain.scope import OutboundRequest, ScopeGuard
from harness_dast.domain.zap_messages import LearnedRequest

SkipReason = Literal[
    "not_success",
    "scope",
    "denied",
    "delete",
    "login",
    "mutating",
    "not_learned",
    "not_planned",
    "not_selected",
    "not_run",
]

_METHOD_RANK: Final = {"PUT": 2, "PATCH": 2, "POST": 1}


class ScanSkip(ApiModel):
    """Operação que NÃO será varrida.

    Attributes:
        operation_id: Operação.
        method: Método HTTP.
        path: Modelo de caminho.
        reason: Motivo curto e estável.
        message: Explicação em português.
    """

    operation_id: str
    method: str
    path: str
    reason: SkipReason
    message: str


class LearnedRef(ApiModel):
    """Liga uma operação à mensagem aprendida no ZAP (resolve `sourceMessageId` depois).

    Attributes:
        operation_id: Operação.
        message_id: Mensagem do ZAP.
    """

    operation_id: str
    message_id: int


class SentRequest(ApiModel):
    """Última requisição de uma operação que passou pelo ZAP, segundo a auditoria.

    Attributes:
        method: Método.
        path: Caminho concreto (sem consulta).
        status: Código HTTP do resultado.
        account: Conta que enviou a requisição no `probe`, ou `None`.
    """

    method: str
    path: str
    status: int | None
    account: str | None = None


@dataclass(frozen=True)
class Candidate:
    """Operação que passou nas regras que não dependem do ZAP."""

    result: OperationResult
    sent: SentRequest

    @property
    def seed_outcome(self) -> str | None:
        """Classe do `probe` quando não foi `success` (a "semente" do ataque, ADR 0050)."""
        return None if self.result.outcome == "success" else self.result.outcome


@dataclass(frozen=True)
class ScanTarget:
    """Uma varredura a executar. `url` e `body` ficam só em memória."""

    operation_id: str
    method: str
    path: str
    message_id: int
    url: str = field(repr=False)
    body: str | None = field(repr=False)
    account: str | None = None
    seed_outcome: str | None = None


@dataclass(frozen=True)
class ScanPlan:
    """O plano: o que varrer, o que pular e as mensagens aprendidas de cada operação."""

    targets: tuple[ScanTarget, ...]
    skipped: tuple[ScanSkip, ...]
    learned: tuple[LearnedRef, ...]


def last_sent(audit: Sequence[AuditEntry]) -> dict[str, SentRequest]:
    """Última requisição de cada operação enviada pela rota do ZAP (linha `result` da auditoria)."""
    found: dict[str, SentRequest] = {}
    for entry in audit:
        if entry.phase == "result" and entry.route == "zap" and entry.status is not None:
            found[entry.operation_id] = SentRequest(
                method=entry.method, path=entry.path, status=entry.status, account=entry.account
            )
    return found


def resolve_include_outcomes(
    from_profile: Sequence[str], requested: Sequence[str] | None
) -> tuple[str, ...]:
    """Classes além de `success` que valem: a flag só escolhe dentro do que o perfil lista.

    Args:
        from_profile: `scan.include_outcomes` do perfil (vem da carta e da aprovação).
        requested: `--include-outcome` da linha de comando; `None` sem flag (vale o perfil) e
            tupla vazia para `--no-include-outcomes` (só `success`).

    Returns:
        As classes aplicadas, na ordem do perfil.

    Raises:
        ConfigError: Classe fora da lista fechada ou que o perfil não lista. Flags só reduzem.
    """
    if requested is None:
        return tuple(from_profile)
    unknown = sorted(set(requested) - EXTRA_OUTCOMES)
    if unknown:
        raise ConfigError(
            "--include-outcome aceita só: " + ", ".join(sorted(EXTRA_OUTCOMES)) + ".",
            hint="success é sempre incluído; erros de servidor e de autenticação nunca.",
        )
    outside = sorted(set(requested) - set(from_profile))
    if outside:
        raise ConfigError(
            "--include-outcome pede classe que o perfil não lista em scan.include_outcomes: "
            + ", ".join(outside)
            + ".",
            hint="Flags só reduzem; só a carta pode autorizar essa classe (peça ao dono do "
            "produto, a pessoa gera o perfil de novo e aprova). O agente não a liga.",
        )
    return tuple(item for item in from_profile if item in set(requested))


def _skip(result: OperationResult, reason: SkipReason, message: str) -> ScanSkip:
    return ScanSkip(
        operation_id=result.operation_id,
        method=result.method,
        path=result.path,
        reason=reason,
        message=message,
    )


def _created_by_run(planned: PlannedOperation, outcomes: Mapping[str, str]) -> bool:
    return bool(planned.depends_on) and all(
        outcomes.get(name) == "success" for name in planned.depends_on
    )


def _decide(
    result: OperationResult,
    planned: PlannedOperation | None,
    *,
    outcomes: Mapping[str, str],
    login_path: str | None,
    config: ScanConfig,
    allowed_outcomes: frozenset[str],
) -> tuple[SkipReason, str] | None:
    if planned is None:
        return "not_planned", "A operação não existe mais no OpenAPI atual; refaça o probe."
    if result.outcome not in allowed_outcomes:
        return "not_success", "O probe não teve sucesso nesta operação; não há requisição válida."
    if result.method == "DELETE":
        return "delete", "DELETE nunca é varrido: o varredor apagaria dados de verdade."
    if login_path is not None and result.method == "POST" and result.path == login_path:
        return "login", "O login não é varrido: senhas inválidas em massa bloqueariam a conta."
    if planned.decision == "skipped_denied":
        return "denied", "O caminho está em scope.deny_paths."
    if planned.decision != "send":
        return "scope", "A operação está fora de scope.allow."
    if result.method in {"PUT", "PATCH"} and not _may_mutate(result, planned, outcomes, config):
        return (
            "mutating",
            f"{result.method} só é varrido sobre recurso criado nesta execução "
            "(flows.yml) ou com scan.mutating_methods no perfil.",
        )
    return None


def _may_mutate(
    result: OperationResult,
    planned: PlannedOperation,
    outcomes: Mapping[str, str],
    config: ScanConfig,
) -> bool:
    return result.method in config.mutating_methods or _created_by_run(planned, outcomes)


def select_candidates(
    probe_operations: Sequence[OperationResult],
    planned: Mapping[str, PlannedOperation],
    sent: Mapping[str, SentRequest],
    *,
    login_path: str | None,
    config: ScanConfig,
    include_outcomes: frozenset[str] = frozenset(),
    only: tuple[str, ...] = (),
) -> tuple[tuple[Candidate, ...], tuple[ScanSkip, ...]]:
    """Aplica as regras que não dependem do ZAP.

    Returns:
        Os candidatos (por conta; em cada conta, leituras e escritas intercaladas, ver `_ordered`)
        e as operações puladas.
    """
    outcomes = {item.operation_id: item.outcome for item in probe_operations}
    allowed = frozenset({"success"}) | (include_outcomes & EXTRA_OUTCOMES)
    candidates: list[Candidate] = []
    skipped: list[ScanSkip] = []
    for result in probe_operations:
        if only and result.operation_id not in only:
            skipped.append(_skip(result, "not_selected", "Fora da seleção de --only."))
            continue
        verdict = _decide(
            result,
            planned.get(result.operation_id),
            outcomes=outcomes,
            login_path=login_path,
            config=config,
            allowed_outcomes=allowed,
        )
        request = sent.get(result.operation_id)
        if verdict is None and request is None:
            verdict = ("not_learned", "A auditoria não registra a requisição desta operação.")
        if verdict is not None:
            skipped.append(_skip(result, *verdict))
        elif request is not None:
            candidates.append(Candidate(result, request))
    return _ordered(candidates), tuple(skipped)


def _ordered(candidates: list[Candidate]) -> tuple[Candidate, ...]:
    """Agrupa por conta (uma troca de token por conta) e intercala leituras e escritas.

    Dentro da conta, as leituras mantêm a ordem do probe e as escritas vão de `POST` a
    `PUT`/`PATCH`. A escrita entra depois de cada bloco de leituras (ver `_interleave`), para que
    um prazo curto cubra as duas classes em vez de gastar tudo nas leituras.
    """
    first_seen: dict[str | None, int] = {}
    for item in candidates:
        first_seen.setdefault(item.sent.account, len(first_seen))
    ordered: list[Candidate] = []
    for account in first_seen:
        mine = [item for item in candidates if item.sent.account == account]
        reads = [item for item in mine if item.result.method not in _METHOD_RANK]
        writes = sorted(
            (item for item in mine if item.result.method in _METHOD_RANK),
            key=lambda item: _METHOD_RANK[item.result.method],
        )
        ordered.extend(_interleave(reads, writes))
    return tuple(ordered)


def _interleave(reads: list[Candidate], writes: list[Candidate]) -> list[Candidate]:
    """Uma escrita depois de cada bloco de `len(reads) // len(writes)` leituras (no mínimo 1).

    Determinístico: começa por leitura (a classe menos arriscada) e, acabado um dos lados, o
    outro segue na sua ordem.
    """
    if not writes:
        return reads
    block = max(1, len(reads) // len(writes))
    result: list[Candidate] = []
    read_at = write_at = 0
    while read_at < len(reads) or write_at < len(writes):
        result.extend(reads[read_at : read_at + block])
        read_at += block
        if write_at < len(writes):
            result.append(writes[write_at])
            write_at += 1
    return result


def _pick(sent: SentRequest, learned: Sequence[LearnedRequest]) -> LearnedRequest | None:
    matches = [
        item
        for item in learned
        if item.method == sent.method
        and urlsplit(item.url).path == sent.path
        and (sent.status is None or item.status in {None, sent.status})
    ]
    return max(matches, key=lambda item: item.message_id, default=None)


def learned_refs(
    sent: Mapping[str, SentRequest], learned: Sequence[LearnedRequest]
) -> tuple[LearnedRef, ...]:
    """Mensagem aprendida de TODA operação enviada (inclusive as que não serão varridas).

    Os alertas passivos do ZAP citam essas mensagens em `sourceMessageId`.
    """
    refs: list[LearnedRef] = []
    for operation_id, request in sent.items():
        found = _pick(request, learned)
        if found is not None:
            refs.append(LearnedRef(operation_id=operation_id, message_id=found.message_id))
    return tuple(refs)


def resolve_targets(
    candidates: Sequence[Candidate],
    sent: Mapping[str, SentRequest],
    learned: Sequence[LearnedRequest],
    guard: ScopeGuard,
) -> ScanPlan:
    """Liga cada candidato à mensagem aprendida e confere o escopo da URL concreta."""
    targets: list[ScanTarget] = []
    skipped: list[ScanSkip] = []
    for candidate in candidates:
        result = candidate.result
        found = _pick(candidate.sent, learned)
        if found is None:
            skipped.append(
                _skip(result, "not_learned", "O ZAP não tem a requisição desta operação.")
            )
            continue
        decision = guard.evaluate(OutboundRequest(method=found.method, url=found.url))
        if decision.verdict != "allowed":
            reason: SkipReason = "denied" if decision.verdict == "denied_path" else "scope"
            skipped.append(_skip(result, reason, "A URL concreta aprendida está fora do escopo."))
            continue
        targets.append(
            ScanTarget(
                operation_id=result.operation_id,
                method=found.method,
                path=result.path,
                message_id=found.message_id,
                url=found.url,
                body=found.body,
                account=candidate.sent.account,
                seed_outcome=candidate.seed_outcome,
            )
        )
    return ScanPlan(tuple(targets), tuple(skipped), learned_refs(sent, learned))
