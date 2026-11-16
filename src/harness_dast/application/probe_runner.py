"""Laço do `probe`: percorre o plano e produz um `OperationResult` por operação.

Cada passo é uma função pequena e nomeada: ignorar (escopo, negação, destrutiva,
dependência), montar a requisição, simular (`--dry-run`) ou enviar, e classificar. As paradas
antecipadas (janela, prazo, ZAP, alvo sem resposta) interrompem o laço e voltam como
`RunOutcome`; nunca são engolidas.
"""

from dataclasses import dataclass, field

from harness_dast.application.account_session import AccountSession
from harness_dast.application.dispatcher import OperationDispatcher, SendOutcome
from harness_dast.application.preview import build_preview
from harness_dast.application.run_support import DeadlineReached, WindowClosed
from harness_dast.application.runner_settings import RunnerSettings, RunOutcome
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.errors import (
    ConfigError,
    ExternalToolError,
    PreflightError,
    ScopeViolation,
    TargetError,
)
from harness_dast.domain.excerpt import sanitize_excerpt
from harness_dast.domain.flow import ResolvedBindings
from harness_dast.domain.http_messages import HttpRequest, HttpResponse
from harness_dast.domain.outcome import Outcome, classify_response, parse_json_body
from harness_dast.domain.probe_conflict import annotate_blocked, conflict_fields
from harness_dast.domain.probe_exchange import ExchangeRecord, build_exchange
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES, UNRESPONSIVE_THRESHOLD
from harness_dast.domain.probe_result import OperationResult, ProbeStatus, TargetData
from harness_dast.domain.request_builder import BuiltRequest
from harness_dast.domain.request_encoding import encode_built_request
from harness_dast.domain.scope import OutboundRequest


@dataclass
class _Prepared:
    built: BuiltRequest
    request: HttpRequest
    uses_flow_values: bool
    generators: dict[str, str]
    unique: dict[str, bool]


@dataclass
class _State:
    results: list[OperationResult] = field(default_factory=list)
    producer_bodies: dict[str, JsonValue] = field(default_factory=dict)
    transport_failures: int = 0
    exchanges: list[ExchangeRecord] = field(default_factory=list)


class ProbeRunner:
    """Executa o plano e devolve o resultado por operação."""

    def __init__(self, settings: RunnerSettings) -> None:
        """Cria o executor.

        Args:
            settings: Entradas fixas do laço.
        """
        self._s = settings
        self._state = _State()

    def run(self, plan: tuple[PlannedOperation, ...]) -> RunOutcome:
        """Percorre o plano até o fim ou até uma parada antecipada.

        Returns:
            Os resultados e o motivo do fim. Janela fechada e prazo esgotado voltam como
            `stopped_window` e `stopped_deadline`; falha do proxy do ZAP como `stopped_zap`;
            alvo sem resposta em sequência como `stopped_target_unresponsive`.
        """
        try:
            for planned in plan:
                self._state.results.append(self._run_one(planned))
                if self._state.transport_failures >= UNRESPONSIVE_THRESHOLD:
                    return self._stopped(
                        plan,
                        "stopped_target_unresponsive",
                        "O alvo ficou sem resposta em várias requisições seguidas; o probe parou.",
                    )
        except WindowClosed as error:
            return self._stopped(plan, "stopped_window", error.message)
        except DeadlineReached as error:
            return self._stopped(plan, "stopped_deadline", error.message)
        except ExternalToolError as error:
            return self._stopped(plan, "stopped_zap", error.message)
        return RunOutcome(
            annotate_blocked(self._state.results, plan),
            "completed",
            None,
            tuple(self._state.exchanges),
        )

    def _stopped(
        self, plan: tuple[PlannedOperation, ...], status: ProbeStatus, message: str
    ) -> RunOutcome:
        return RunOutcome(
            annotate_blocked(self._state.results, plan),
            status,
            message,
            tuple(self._state.exchanges),
        )

    def _run_one(self, planned: PlannedOperation) -> OperationResult:
        if planned.decision != "send":
            return self._result(planned, planned.decision, message=planned.reason)
        missing = [name for name in planned.depends_on if name not in self._state.producer_bodies]
        if missing and self._s.dispatcher is not None:
            return self._result(
                planned,
                "skipped_dependency",
                message="O produtor de que esta operação depende não teve sucesso.",
                hint="Corrija primeiro a operação produtora (veja o resultado dela).",
            )
        prepared = self._prepare(planned)
        if isinstance(prepared, OperationResult):
            return prepared
        dispatcher = self._s.dispatcher
        if dispatcher is None:
            return self._dry_run(planned, prepared)
        return self._execute(planned, prepared, dispatcher)

    def _prepare(self, planned: PlannedOperation) -> _Prepared | OperationResult:
        operation = self._s.operations[planned.operation_id]
        self._s.recorder.take()
        self._s.recorder.take_unique()
        try:
            bindings = self._bindings(planned)
            built = self._s.builder.build(operation, bindings)
            request = encode_built_request(
                built, base_url=self._s.base_url, account=self._s.account_for(planned)
            )
        except TargetError as error:
            return self._result(
                planned, "skipped_dependency", message=error.message, hint=error.hint
            )
        except ConfigError as error:
            return self._result(planned, "build_error", message=error.message, hint=error.hint)
        return _Prepared(
            built,
            request,
            bool(planned.depends_on),
            self._s.recorder.take(),
            self._s.recorder.take_unique(),
        )

    def _bindings(self, planned: PlannedOperation) -> ResolvedBindings:
        if self._s.flows is None or not planned.depends_on or self._s.dispatcher is None:
            return ResolvedBindings()
        return self._s.flows.resolve_bindings(planned.operation_id, self._state.producer_bodies)

    def _dry_run(self, planned: PlannedOperation, prepared: _Prepared) -> OperationResult:
        decision = self._s.guard.evaluate(
            OutboundRequest(method=prepared.request.method, url=prepared.request.url)
        )
        if decision.verdict != "allowed":
            return self._scope_result(planned, decision.verdict == "denied_path", decision.reason)
        preview = build_preview(
            self._s.operations[planned.operation_id],
            prepared.built,
            prepared.generators,
            uses_flow_values=prepared.uses_flow_values,
        )
        return self._result(planned, "dry_run", preview=preview)

    def _execute(
        self, planned: PlannedOperation, prepared: _Prepared, dispatcher: OperationDispatcher
    ) -> OperationResult:
        anonymous = self._is_login(planned)
        started = self._s.clock.now()
        request = (
            prepared.request
            if not anonymous
            else prepared.request.model_copy(update={"account": None})
        )
        try:
            sent = dispatcher.send(request, None if anonymous else self._session_for(request))
        except (WindowClosed, DeadlineReached):
            raise
        except ScopeViolation as error:
            denied = (
                self._s.guard.evaluate(
                    OutboundRequest(method=request.method, url=request.url)
                ).verdict
                == "denied_path"
            )
            return self._scope_result(planned, denied, error.message)
        except PreflightError as error:
            return self._result(planned, "auth_error", message=error.message, hint=error.hint)
        elapsed = int((self._s.clock.now() - started).total_seconds() * 1000)
        return self._classified(planned, request, sent, elapsed, prepared)

    def _session_for(self, request: HttpRequest) -> AccountSession | None:
        pool = self._s.sessions
        if pool is None or request.account is None:
            return None
        return pool.get(request.account)

    def _classified(
        self,
        planned: PlannedOperation,
        request: HttpRequest,
        sent: SendOutcome,
        elapsed: int,
        prepared: _Prepared,
    ) -> OperationResult:
        response = sent.response
        failed_transport = response is None or response.status in TRANSPORT_FAILURE_STATUSES
        self._state.transport_failures = (
            self._state.transport_failures + 1 if failed_transport else 0
        )
        common = {"duration_ms": elapsed, "attempts": sent.attempts, "account": request.account}
        if response is None:
            error = sent.transport_error
            return self._result(
                planned,
                "timeout",
                message=error.message if error else None,
                hint=error.hint if error else None,
                **common,
            )
        outcome = classify_response(
            response,
            method=request.method,
            success_rule=self._s.success_rule,
            csrf=self._s.csrf,
            error_codes=self._s.error_codes,
            is_login=self._is_login(planned),
        )
        if outcome == "success" and planned.is_producer:
            self._state.producer_bodies[planned.operation_id] = parse_json_body(response)
        if outcome == "success":
            self._remember(planned, request, response)
        return self._result(
            planned,
            outcome,
            status=response.status,
            conflict_fields=tuple(
                name
                for name in conflict_fields(
                    response,
                    self._s.operations[planned.operation_id],
                    prepared.built.body,
                    prepared.unique,
                )
                if self._s.vault.mask(name) == name
            )
            if outcome == "conflict"
            else (),
            untrusted_target_data=None if outcome == "success" else self._excerpt(response),
            redirect_in_scope=self._redirect_in_scope(request, response)
            if outcome == "redirect"
            else None,
            **common,
        )

    def _remember(
        self, planned: PlannedOperation, request: HttpRequest, response: HttpResponse
    ) -> None:
        """Guarda o pedido com sucesso para o teste de autorização (ADR 0027)."""
        record = build_exchange(
            request=request,
            path_template=planned.path,
            status=response.status,
            base_url=self._s.base_url,
            mask=self._s.vault.mask,
        )
        if record is not None:
            self._state.exchanges.append(record)

    def _excerpt(self, response: HttpResponse) -> TargetData:
        return TargetData(
            excerpt=sanitize_excerpt(response.body, self._s.vault.mask),
            content_type=response.content_type,
            retry_after=response.retry_after,
        )

    def _redirect_in_scope(self, request: HttpRequest, response: HttpResponse) -> bool:
        if not response.location:
            return False
        try:
            self._s.guard.ensure_redirect_allowed(
                request=OutboundRequest(method=request.method, url=request.url),
                location=response.location,
                method="GET",
            )
        except ScopeViolation:
            return False
        return True

    def _is_login(self, planned: PlannedOperation) -> bool:
        return (
            self._s.login_path is not None
            and planned.method == "POST"
            and planned.path == self._s.login_path
        )

    def _scope_result(
        self, planned: PlannedOperation, denied: bool, reason: str | None
    ) -> OperationResult:
        outcome: Outcome = "skipped_denied" if denied else "skipped_scope"
        return self._result(
            planned,
            outcome,
            message=reason,
            hint="A URL concreta saiu do escopo; nada foi enviado. Revise a regra de dados.",
        )

    def _result(
        self, planned: PlannedOperation, outcome: Outcome, **fields: object
    ) -> OperationResult:
        return OperationResult.model_validate(
            {
                "operation_id": planned.operation_id,
                "method": planned.method,
                "path": planned.path,
                "outcome": outcome,
                **fields,
            }
        )
