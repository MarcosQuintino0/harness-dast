"""Entradas e saída do laço do `probe`."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.ports import Clock, SecretVault
from harness_dast.application.preview import RecordingSource
from harness_dast.application.session_pool import SessionPool
from harness_dast.domain.api_model import Operation
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_config import ErrorCodes, JsonFieldRule
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.probe_plan import PlannedOperation
from harness_dast.domain.probe_result import OperationResult, ProbeStatus
from harness_dast.domain.request_builder import RequestBuilder
from harness_dast.domain.scope import ScopeGuard


@dataclass(frozen=True)
class RunnerSettings:
    """Entradas fixas do laço.

    Attributes:
        operations: Operações do OpenAPI por identificador.
        flows: Encadeamento do produto, ou `None`.
        builder: Montador de requisições (uma instância por execução).
        recorder: Registro de geradores usado pela prévia do `--dry-run`.
        guard: Guarda de escopo do perfil.
        base_url: URL base do ambiente.
        account_for: Escolhe o apelido da conta que envia cada operação do plano.
        success_rule: Regra de corpo de `probe.success`, ou `None`.
        csrf: Configuração de CSRF do perfil, ou `None`.
        error_codes: Mapa de códigos de erro do perfil (`probe.error_codes`), ou `None`.
        login_path: Caminho do login (operação enviada sem sessão), ou `None`.
        vault: Registro de segredos (mascara os trechos de resposta).
        clock: Relógio injetado (duração).
        dispatcher: Despachante; `None` no `--dry-run`.
        sessions: Sessões das contas (um login por conta); `None` no `--dry-run`.
    """

    operations: Mapping[str, Operation]
    flows: FlowSpec | None
    builder: RequestBuilder
    recorder: RecordingSource
    guard: ScopeGuard
    base_url: str
    account_for: Callable[[PlannedOperation], str]
    success_rule: JsonFieldRule | None
    csrf: CsrfConfig | None
    error_codes: ErrorCodes | None
    login_path: str | None
    vault: SecretVault
    clock: Clock
    dispatcher: OperationDispatcher | None = None
    sessions: SessionPool | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Resultado do laço.

    Attributes:
        results: Resultado por operação processada, na ordem de execução.
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada antecipada.
        exchanges: Pedidos com sucesso, repetíveis pelo teste de autorização (`exchanges.json`).
    """

    results: tuple[OperationResult, ...]
    status: ProbeStatus
    stop_message: str | None
    exchanges: tuple[ExchangeRecord, ...] = ()
