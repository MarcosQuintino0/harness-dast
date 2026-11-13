"""Entradas e saída do laço do `probe`."""

from collections.abc import Mapping
from dataclasses import dataclass

from harness_dast.application.account_session import AccountSession
from harness_dast.application.dispatcher import OperationDispatcher
from harness_dast.application.ports import Clock, SecretVault
from harness_dast.application.preview import RecordingSource
from harness_dast.domain.api_model import Operation
from harness_dast.domain.auth import CsrfConfig
from harness_dast.domain.flow import FlowSpec
from harness_dast.domain.probe_config import JsonFieldRule
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
        account: Apelido da conta que envia.
        success_rule: Regra de corpo de `probe.success`, ou `None`.
        csrf: Configuração de CSRF do perfil, ou `None`.
        login_path: Caminho do login (operação enviada sem sessão), ou `None`.
        vault: Registro de segredos (mascara os trechos de resposta).
        clock: Relógio injetado (duração).
        dispatcher: Despachante; `None` no `--dry-run`.
        session: Sessão da conta; `None` no `--dry-run`.
    """

    operations: Mapping[str, Operation]
    flows: FlowSpec | None
    builder: RequestBuilder
    recorder: RecordingSource
    guard: ScopeGuard
    base_url: str
    account: str
    success_rule: JsonFieldRule | None
    csrf: CsrfConfig | None
    login_path: str | None
    vault: SecretVault
    clock: Clock
    dispatcher: OperationDispatcher | None = None
    session: AccountSession | None = None


@dataclass(frozen=True)
class RunOutcome:
    """Resultado do laço.

    Attributes:
        results: Resultado por operação processada, na ordem de execução.
        status: `completed` ou o motivo da parada antecipada.
        stop_message: Explicação da parada antecipada.
    """

    results: tuple[OperationResult, ...]
    status: ProbeStatus
    stop_message: str | None
