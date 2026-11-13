"""Laço do teste de autorização: envia os pedidos do plano e decide, no domínio, o veredito.

Todo pedido passa por `OperationDispatcher` sobre o `GuardedSender` (o mesmo caminho do
`probe`: escopo, `deny_paths`, métodos, taxa, janela, prazo, trava e auditoria). Este laço só
REPETE pedidos gravados em `exchanges.json`: monta a URL a partir do alvo gravado e não inventa
caminho nem método. Nenhum valor de resposta é guardado: só o veredito, os códigos e os NOMES de
campo vão para o resultado. Paradas antecipadas (janela, prazo, ZAP, alvo sem resposta)
interrompem o laço e voltam como `AuthzOutcome`; nunca são engolidas.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.api_schema import JsonValue, Schema
from harness_dast.domain.authz_compare import (
    bodies_equivalent,
    holds_value,
    injected_effect,
    is_success_status,
    judge_replay,
    parse_json,
    unexpected_fields,
)
from harness_dast.domain.authz_config import AuthzCheck, AuthzConfig, MassAssignmentField
from harness_dast.domain.authz_findings import (
    excessive_data_finding,
    horizontal_finding,
    mass_assignment_finding,
    vertical_finding,
)
from harness_dast.domain.authz_plan import MassTask, Planned, ReplayTask
from harness_dast.domain.authz_result import AuthzFinding, AuthzNotTested, CheckSummary
from harness_dast.domain.errors import ExternalToolError, PreflightError, ScopeViolation
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES, UNRESPONSIVE_THRESHOLD
from harness_dast.domain.probe_result import ProbeStatus
from harness_dast.domain.request_encoding import join_url

DENIED_STATUSES = frozenset({401, 403})
"""No acesso vertical só 401 e 403 provam que o servidor negou; 400, 404 e 409 são ambíguos."""


class _Stop(Exception):
    """Parada antecipada que o laço traduz em `AuthzOutcome`."""

    def __init__(self, status: ProbeStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Reply:
    """Resposta reduzida ao que as decisões usam (o corpo só vive em memória).

    Attributes:
        status: Código HTTP, ou `None` sem resposta.
        body: Corpo da resposta (nunca gravado).
        problem: `scope` (pedido recusado pelo escopo) ou `account` (login recusado), ou `None`.
    """

    status: int | None
    body: bytes = b""
    problem: str | None = None


@dataclass
class CheckResult:
    """Resultado acumulado de uma verificação."""

    findings: list[AuthzFinding] = field(default_factory=list)
    not_tested: list[AuthzNotTested] = field(default_factory=list)
    candidates: int = 0
    tested: int = 0


@dataclass(frozen=True)
class AuthzOutcome:
    """Resultado do laço.

    Attributes:
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada.
        checks: Uma linha por verificação pedida.
        findings: Achados, na ordem das verificações.
        not_tested: O que não foi testado e por quê.
        requests_sent: Requisições enviadas.
        accounts: Contas que enviaram.
    """

    status: ProbeStatus
    stop_message: str | None
    checks: tuple[CheckSummary, ...]
    findings: tuple[AuthzFinding, ...]
    not_tested: tuple[AuthzNotTested, ...]
    requests_sent: int
    accounts: tuple[str, ...]


@dataclass(frozen=True)
class AuthzPlans:
    """Planos de cada verificação (calculados no domínio antes de enviar)."""

    horizontal: Planned[ReplayTask]
    excessive: Planned[ExchangeRecord]
    vertical: Planned[ReplayTask]
    mass: Planned[MassTask]


@dataclass(frozen=True)
class AuthzSettings:
    """Entradas fixas do laço.

    Attributes:
        product: Produto.
        base_url: URL base do ambiente.
        config: Bloco `authz` do perfil.
        roles: Papel de cada conta (apelido -> papel).
        operations: Operações do OpenAPI por identificador.
        dispatcher: Despachante (escopo, taxa, janela, prazo, auditoria).
        sessions: Sessões das contas (um login por conta).
    """

    product: str
    base_url: str
    config: AuthzConfig
    roles: Mapping[str, str]
    operations: Mapping[str, Operation]
    dispatcher: OperationDispatcher
    sessions: SessionPool


class AuthzRunner:
    """Executa as verificações pedidas (veja o docstring do módulo)."""

    def __init__(self, settings: AuthzSettings) -> None:
        """Cria o executor.

        Args:
            settings: Entradas fixas do laço.
        """
        self._s = settings
        self._volatile = settings.config.volatile_names()
        self._cache: dict[tuple[str, str], Reply] = {}
        self._sent = 0
        self._failures = 0
        self._accounts: list[str] = []

    def run(self, checks: tuple[AuthzCheck, ...], plans: AuthzPlans) -> AuthzOutcome:
        """Roda as verificações na ordem recebida.

        Returns:
            O resultado; janela fechada e prazo esgotado voltam como `stopped_window` e
            `stopped_deadline`, falha do proxy como `stopped_zap` e alvo sem resposta em
            sequência como `stopped_target_unresponsive`.
        """
        results: dict[AuthzCheck, CheckResult] = {}
        status: ProbeStatus = "completed"
        message: str | None = None
        try:
            for check in checks:
                results[check] = self._run_check(check, plans)
        except _Stop as stop:
            status, message = stop.status, stop.message
        except WindowClosed as error:
            status, message = "stopped_window", error.message
        except DeadlineReached as error:
            status, message = "stopped_deadline", error.message
        except ExternalToolError as error:
            status, message = "stopped_zap", error.message
        return self._outcome(checks, results, status, message)

    def _run_check(self, check: AuthzCheck, plans: AuthzPlans) -> CheckResult:
        if check == "horizontal":
            return self._horizontal(plans.horizontal)
        if check == "excessive_data":
            return self._excessive(plans.excessive)
        if check == "vertical":
            return self._vertical(plans.vertical)
        return self._mass(plans.mass)

    # --- envio -------------------------------------------------------------------------

    def _send(
        self,
        exchange: ExchangeRecord,
        account: str,
        *,
        body: JsonValue = None,
        with_body: bool = False,
        method: str | None = None,
    ) -> Reply:
        text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if with_body else None
        payload = text if text is not None else exchange.body
        headers = (
            (("Content-Type", exchange.content_type),) if payload and exchange.content_type else ()
        )
        request = HttpRequest(
            method=method or exchange.method,
            url=join_url(self._s.base_url, exchange.target),
            headers=headers,
            body=payload.encode("utf-8") if payload else None,
            operation_id=f"authz:{exchange.operation_id}",
            account=account,
        )
        try:
            session = self._s.sessions.get(account)
            sent = self._s.dispatcher.send(request, session)
        except (WindowClosed, DeadlineReached):
            raise
        except ScopeViolation:
            return Reply(None, problem="scope")
        except PreflightError:
            return Reply(None, problem="account")
        if account not in self._accounts:
            self._accounts.append(account)
        self._sent += sent.attempts
        response = sent.response
        failed = response is None or response.status in TRANSPORT_FAILURE_STATUSES
        self._failures = self._failures + 1 if failed else 0
        if self._failures >= UNRESPONSIVE_THRESHOLD:
            raise _Stop(
                "stopped_target_unresponsive",
                "O alvo ficou sem resposta em várias requisições seguidas; o authz parou.",
            )
        if response is None:
            return Reply(None)
        return Reply(response.status, response.body)

    def _baseline(self, exchange: ExchangeRecord) -> Reply:
        key = (exchange.account, exchange.target)
        if key not in self._cache:
            self._cache[key] = self._send(exchange, exchange.account)
        return self._cache[key]

    # --- verificações ------------------------------------------------------------------

    def _horizontal(self, plan: Planned[ReplayTask]) -> CheckResult:
        out = CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
        for task in plan.tasks:
            exchange = task.exchange
            base = self._baseline(exchange)
            if base.problem is not None:
                out.not_tested.append(self._problem_note("horizontal", exchange, base))
                continue
            if not is_success_status(base.status):
                out.not_tested.append(
                    self._note(
                        "horizontal",
                        exchange,
                        "baseline_failed",
                        "A conta dona não repetiu o pedido com sucesso agora "
                        f"(status {base.status}); sem linha de base não há o que comparar.",
                    )
                )
                continue
            replay = self._send(exchange, task.actor[0])
            if replay.problem is not None:
                out.not_tested.append(self._problem_note("horizontal", exchange, replay))
                continue
            same = bodies_equivalent(base.body, replay.body, self._volatile)
            verdict = judge_replay(base.status, replay.status, equivalent=same)
            if verdict == "error":
                out.not_tested.append(self._inconclusive("horizontal", exchange, replay))
                continue
            out.tested += 1
            if verdict == "allowed_equivalent" and base.status is not None and replay.status:
                out.findings.append(
                    horizontal_finding(
                        product=self._s.product,
                        operation_id=exchange.operation_id,
                        method=exchange.method,
                        path_template=exchange.path,
                        actor=task.actor,
                        owner=task.owner,
                        statuses=(base.status, replay.status),
                    )
                )
        return out

    def _excessive(self, plan: Planned[ExchangeRecord]) -> CheckResult:
        out = CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
        for exchange in plan.tasks:
            reply = self._baseline(exchange)
            operation = self._s.operations.get(exchange.operation_id)
            schema = _response_schema(operation, reply.status)
            body = parse_json(reply.body) if is_success_status(reply.status) else None
            if schema is None or body is None:
                out.not_tested.append(self._no_schema_note(exchange, reply, schema is None))
                continue
            out.tested += 1
            fields = unexpected_fields(schema, body)
            if fields and reply.status is not None:
                role = self._s.roles.get(exchange.account)
                out.findings.append(
                    excessive_data_finding(
                        product=self._s.product,
                        operation_id=exchange.operation_id,
                        method=exchange.method,
                        path_template=exchange.path,
                        actor=(exchange.account, role),
                        status=reply.status,
                        fields=fields,
                    )
                )
        return out

    def _vertical(self, plan: Planned[ReplayTask]) -> CheckResult:
        out = CheckResult(not_tested=list(plan.not_tested), candidates=len(plan.tasks))
        for task in plan.tasks:
            exchange = task.exchange
            reply = self._send(exchange, task.actor[0])
            if reply.problem is not None:
                out.not_tested.append(self._problem_note("vertical", exchange, reply))
            elif is_success_status(reply.status) and reply.status is not None:
                out.tested += 1
                out.findings.append(
                    vertical_finding(
                        product=self._s.product,
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
                out.not_tested.append(self._inconclusive("vertical", exchange, reply))
        return out

    def _mass(self, plan: Planned[MassTask]) -> CheckResult:
        fields = self._s.config.mass_assignment_fields
        out = CheckResult(
            not_tested=list(plan.not_tested), candidates=len(plan.tasks) * len(fields)
        )
        for task in plan.tasks:
            for extra in fields:
                self._mass_one(task, extra, out)
        return out

    def _mass_one(self, task: MassTask, extra: MassAssignmentField, out: CheckResult) -> None:
        exchange = task.exchange
        original = _as_object(exchange.body)
        if original is None or extra.name in original:
            out.not_tested.append(
                self._note(
                    "mass_assignment",
                    exchange,
                    "field_in_body",
                    f"O campo '{extra.name}' já faz parte do corpo do probe; não é extra.",
                )
            )
            return
        before = self._read(task)
        put = self._send(
            exchange, exchange.account, body={**original, extra.name: extra.value}, with_body=True
        )
        if put.problem is not None:
            out.not_tested.append(self._problem_note("mass_assignment", exchange, put))
            return
        if put.status is None or put.status >= 500:
            out.not_tested.append(self._inconclusive("mass_assignment", exchange, put))
            return
        out.tested += 1
        if not is_success_status(put.status):
            return
        after = self._read(task, fallback=put)
        changed, previous = injected_effect(before, after, extra.name, extra.value)
        if not changed:
            return
        restored = self._restore(task, original, extra, changed, previous)
        role = self._s.roles.get(exchange.account)
        out.findings.append(
            mass_assignment_finding(
                product=self._s.product,
                operation_id=exchange.operation_id,
                method=exchange.method,
                path_template=exchange.path,
                actor=(exchange.account, role),
                sent_field=extra.name,
                changed=changed,
                status=put.status,
                restored=restored,
            )
        )

    def _read(self, task: MassTask, fallback: Reply | None = None) -> JsonValue | None:
        """Corpo JSON da leitura seguinte (um GET provado pelo `probe`) ou da própria resposta."""
        if task.read is None:
            return parse_json(fallback.body) if fallback is not None else None
        reply = self._send(task.read, task.read.account)
        return parse_json(reply.body) if is_success_status(reply.status) else None

    def _restore(
        self,
        task: MassTask,
        original: dict[str, JsonValue],
        extra: MassAssignmentField,
        changed: tuple[str, ...],
        previous: JsonValue,
    ) -> bool | None:
        """Tenta devolver o valor anterior; `None` se não havia valor escalar para devolver."""
        if previous is None or isinstance(previous, dict | list):
            return None
        exchange = task.exchange
        self._send(
            exchange, exchange.account, body={**original, extra.name: previous}, with_body=True
        )
        again = self._read(task)
        return again is not None and not holds_value(again, changed, extra.value)

    # --- anotações ---------------------------------------------------------------------

    @staticmethod
    def _note(
        check: AuthzCheck, exchange: ExchangeRecord, reason: str, message: str
    ) -> AuthzNotTested:
        return AuthzNotTested(
            check=check,
            operation_id=exchange.operation_id,
            method=exchange.method,
            path=exchange.path,
            reason=reason,
            message=message,
        )

    def _problem_note(
        self, check: AuthzCheck, exchange: ExchangeRecord, reply: Reply
    ) -> AuthzNotTested:
        if reply.problem == "scope":
            return self._note(
                check,
                exchange,
                "scope_denied",
                "O escopo do perfil recusou o pedido (caminho negado ou método fora do escopo); "
                "nada foi enviado.",
            )
        return self._note(
            check,
            exchange,
            "account_unavailable",
            "Uma conta necessária não conseguiu abrir sessão (login recusado).",
        )

    def _inconclusive(
        self, check: AuthzCheck, exchange: ExchangeRecord, reply: Reply
    ) -> AuthzNotTested:
        return self._note(
            check,
            exchange,
            "inconclusive",
            f"Resposta sem conclusão (status {reply.status}); não conta como seguro.",
        )

    def _no_schema_note(
        self, exchange: ExchangeRecord, reply: Reply, missing_schema: bool
    ) -> AuthzNotTested:
        if missing_schema:
            return self._note(
                "excessive_data",
                exchange,
                "no_response_schema",
                "O OpenAPI não declara o esquema da resposta de sucesso desta operação.",
            )
        return self._note(
            "excessive_data",
            exchange,
            "no_json_response",
            f"A resposta (status {reply.status}) não é um JSON de sucesso para comparar.",
        )

    def _outcome(
        self,
        checks: tuple[AuthzCheck, ...],
        results: Mapping[AuthzCheck, CheckResult],
        status: ProbeStatus,
        message: str | None,
    ) -> AuthzOutcome:
        summaries: list[CheckSummary] = []
        findings: list[AuthzFinding] = []
        not_tested: list[AuthzNotTested] = []
        for check in checks:
            result = results.get(check)
            if result is None:
                summaries.append(
                    CheckSummary(
                        check=check,
                        status="skipped",
                        message="Não rodou: a execução parou antes desta verificação.",
                    )
                )
                continue
            findings.extend(result.findings)
            not_tested.extend(result.not_tested)
            summaries.append(_summary(check, result))
        return AuthzOutcome(
            status=status,
            stop_message=message,
            checks=tuple(summaries),
            findings=tuple(findings),
            not_tested=tuple(not_tested),
            requests_sent=self._sent,
            accounts=tuple(self._accounts),
        )


def _summary(check: AuthzCheck, result: CheckResult) -> CheckSummary:
    skipped = result.tested == 0
    return CheckSummary(
        check=check,
        status="skipped" if skipped else "completed",
        candidates=result.candidates,
        tested=result.tested,
        findings=len(result.findings),
        message="Nenhuma operação pôde ser testada; veja not_tested." if skipped else None,
    )


def _as_object(text: str | None) -> dict[str, JsonValue] | None:
    if text is None:
        return None
    try:
        parsed: JsonValue = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _response_schema(operation: Operation | None, status: int | None) -> Schema | None:
    if operation is None or status is None:
        return None
    exact = [r for r in operation.success_responses if r.status == str(status)]
    success = [r for r in operation.success_responses if r.status.startswith("2")]
    for response in (*exact, *success):
        if response.body_schema is not None:
            return response.body_schema
    return None
