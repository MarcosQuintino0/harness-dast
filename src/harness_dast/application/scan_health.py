"""Guarda de saúde do alvo durante o `scan`.

O spike do M0 viu o alvo saturar (CPU a 100% por minutos) por causa da varredura. A guarda
envia UMA requisição barata e dentro do escopo (`probe.health_path` ou a raiz) entre as
varreduras e, de tempos em tempos, durante cada uma. Falhas seguidas, depois de esperas para o
alvo se recuperar, encerram o `scan` com `ScanTargetDown` (saída 6). Sem requisição de saúde
no escopo a guarda fica desligada e o resultado diz isso.
"""

from typing import Final

from harness_dast.application.ports import Clock, Sleeper
from harness_dast.application.run_support import GuardedSender
from harness_dast.domain.errors import TargetError, TargetTimeout, TargetUnreachable
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_policy import TRANSPORT_FAILURE_STATUSES
from harness_dast.domain.scan_result import HealthSummary
from harness_dast.domain.scope import OutboundRequest, ScopeGuard

HEALTH_OPERATION_ID: Final = "scan.health"
FAILURE_LIMIT: Final = 3
"""Falhas seguidas (depois de esperar a recuperação) que dão o alvo por indisponível."""

RECOVERY_WAIT_SECONDS: Final = 10.0
"""Espera entre duas conferências que falharam, para dar tempo ao alvo."""

INTERVAL_SECONDS: Final = 30.0
"""Intervalo entre conferências durante uma varredura longa."""


class ScanTargetDown(TargetError):
    """O alvo parou de responder durante o `scan`."""


class TargetHealth:
    """Confere a saúde do alvo e conta as falhas."""

    def __init__(
        self,
        *,
        sender: GuardedSender,
        guard: ScopeGuard,
        url: str,
        clock: Clock,
        sleeper: Sleeper,
    ) -> None:
        """Cria a guarda.

        Args:
            sender: Emissor protegido (escopo, ritmo, janela, auditoria).
            guard: Guarda de escopo, para saber se a URL de saúde pode ser enviada.
            url: URL de um GET leve.
            clock: Relógio injetado.
            sleeper: Espera injetada.
        """
        self._sender = sender
        self._request = HttpRequest(
            method="GET", url=url, operation_id=HEALTH_OPERATION_ID, account=None
        )
        decision = guard.evaluate(OutboundRequest(method="GET", url=url))
        self._enabled = decision.verdict == "allowed"
        self._clock = clock
        self._sleeper = sleeper
        self._last = clock.now()
        self._checks = 0
        self._failures = 0

    @property
    def summary(self) -> HealthSummary:
        """Contagens para o resultado."""
        return HealthSummary(enabled=self._enabled, checks=self._checks, failures=self._failures)

    def ensure_alive(self) -> None:
        """Confere a saúde, esperando a recuperação entre falhas.

        Raises:
            ScanTargetDown: `FAILURE_LIMIT` falhas seguidas.
            ScopeViolation: Janela fechada ou prazo esgotado (vem do emissor).
            ExternalToolError: O proxy do ZAP não respondeu.
        """
        if not self._enabled:
            return
        consecutive = 0
        while True:
            if self._check_once():
                self._last = self._clock.now()
                return
            consecutive += 1
            if consecutive >= FAILURE_LIMIT:
                raise ScanTargetDown(
                    "O alvo parou de responder durante a varredura.",
                    hint="Aguarde o alvo se recuperar e reduza zap_threads_per_host ou "
                    "requests_per_second antes de repetir o scan.",
                )
            self._sleeper.sleep(RECOVERY_WAIT_SECONDS)

    def tick(self) -> None:
        """Confere a saúde se já passou `INTERVAL_SECONDS` desde a última conferência."""
        if self._enabled and (self._clock.now() - self._last).total_seconds() >= INTERVAL_SECONDS:
            self.ensure_alive()

    def _check_once(self) -> bool:
        self._checks += 1
        try:
            response = self._sender.send(self._request)
        except (TargetTimeout, TargetUnreachable):
            self._failures += 1
            return False
        if response.status in TRANSPORT_FAILURE_STATUSES:
            self._failures += 1
            return False
        return True
