"""Peças comuns de uma execução que fala com o alvo: janela, prazo, ritmo, auditoria e o envio.

`GuardedSender` é o único caminho de saída da camada `application`: toda requisição passa
por `domain.http_messages.approve` (que chama o `ScopeGuard`), é auditada ANTES do envio e
só então chega ao `TargetClient`, que por sua vez só aceita `ApprovedRequest`.
"""

from datetime import datetime, timedelta

from harness_dast.application.ports import Clock, KillSwitch, RunStore, Sleeper, TargetClient
from harness_dast.domain.audit import decision_entry, result_entry
from harness_dast.domain.errors import HarnessError, ScopeViolation
from harness_dast.domain.http_messages import HttpRequest, HttpResponse, approve
from harness_dast.domain.probe_policy import TokenBucket
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import ScopeGuard


class WindowClosed(ScopeViolation):
    """A autorização venceu ou a janela de execução fechou durante a execução."""


class KillSwitchEngaged(WindowClosed):
    """A trava de emergência (`hdast stop`) foi acionada durante a execução."""


class DeadlineReached(ScopeViolation):
    """O tempo máximo da execução (`limits.max_duration_minutes`) acabou."""


class RunGate:
    """Confere, antes de cada requisição, autorização, janela e prazo da execução."""

    def __init__(
        self,
        profile: ProductProfile,
        clock: Clock,
        started_at: datetime,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        """Cria o portão.

        Args:
            profile: Perfil da execução.
            clock: Relógio injetado.
            started_at: Instante de início; o prazo é este instante mais
                `limits.max_duration_minutes`.
            kill_switch: Trava de emergência a consultar; `None` não consulta.
        """
        self._profile = profile
        self._kill_switch = kill_switch
        self._clock = clock
        self._deadline = started_at + timedelta(minutes=profile.limits.max_duration_minutes)

    def check(self) -> None:
        """Garante que a execução ainda pode enviar requisições.

        Raises:
            KillSwitchEngaged: A trava de emergência foi acionada.
            DeadlineReached: O prazo acabou.
            WindowClosed: A autorização venceu ou nenhuma janela está aberta.
        """
        if self._kill_switch is not None and self._kill_switch.engaged():
            raise KillSwitchEngaged(
                "A trava de emergência (hdast stop) foi acionada.",
                hint="Recrie a pilha com hdast stack up para voltar a enviar requisições.",
            )
        now = self._clock.now()
        if now >= self._deadline:
            raise DeadlineReached(
                "O tempo máximo da execução (limits.max_duration_minutes) acabou.",
                hint="Rode de novo com menos operações (--only) ou peça mais tempo ao dono.",
            )
        try:
            self._profile.ensure_runnable(now)
        except ScopeViolation as error:
            raise WindowClosed(error.message, hint=error.hint) from None


class AuditTrail:
    """Grava `audit.jsonl`: a decisão antes do envio e o resultado depois."""

    def __init__(self, store: RunStore, run_id: str, clock: Clock) -> None:
        """Cria a trilha de uma execução.

        Args:
            store: Armazém dos arquivos da execução.
            run_id: Identificador da execução.
            clock: Relógio injetado (carimbo das linhas).
        """
        self._store = store
        self._run_id = run_id
        self._clock = clock
        self._seq = 0

    def decide(self, request: HttpRequest, reason: str | None) -> int:
        """Grava a linha de decisão (`reason` não nulo = recusada) e devolve o `seq`."""
        self._seq += 1
        self._store.append_audit(
            self._run_id, decision_entry(self._seq, self._clock.now(), request, reason=reason)
        )
        return self._seq

    def finish(
        self, seq: int, request: HttpRequest, *, status: int | None, error: str | None, ms: int
    ) -> None:
        """Grava a linha de resultado da requisição `seq`."""
        entry = result_entry(
            seq, self._clock.now(), request, status=status, error=error, duration_ms=ms
        )
        self._store.append_audit(self._run_id, entry)


class RateLimiter:
    """Espera o necessário para respeitar `limits.requests_per_second` (relógio injetado)."""

    def __init__(self, requests_per_second: float, clock: Clock, sleeper: Sleeper) -> None:
        """Cria o limitador.

        Args:
            requests_per_second: Taxa do perfil.
            clock: Relógio injetado.
            sleeper: Espera injetada.
        """
        self._bucket = TokenBucket(requests_per_second)
        self._clock = clock
        self._sleeper = sleeper

    def wait(self) -> None:
        """Bloqueia até a próxima vaga."""
        delay = self._bucket.reserve(self._clock.now().timestamp())
        if delay > 0:
            self._sleeper.sleep(delay)


class GuardedSender:
    """Envia requisições ao alvo somente depois de portão, ritmo, escopo e auditoria."""

    def __init__(
        self,
        *,
        guard: ScopeGuard,
        client: TargetClient,
        gate: RunGate,
        limiter: RateLimiter,
        trail: AuditTrail,
        clock: Clock,
    ) -> None:
        """Cria o emissor.

        Args:
            guard: Guarda de escopo do perfil.
            client: Cliente HTTP (só aceita requisições aprovadas).
            gate: Portão de janela e prazo.
            limiter: Limitador de taxa.
            trail: Trilha de auditoria.
            clock: Relógio injetado (duração).
        """
        self._guard = guard
        self._client = client
        self._gate = gate
        self._limiter = limiter
        self._trail = trail
        self._clock = clock

    def send(self, request: HttpRequest) -> HttpResponse:
        """Envia a requisição.

        Ordem fixa: ritmo, portão (janela e prazo), `ScopeGuard`, linha de decisão, envio,
        linha de resultado.

        Raises:
            WindowClosed: Autorização vencida ou janela fechada.
            DeadlineReached: Prazo da execução esgotado.
            ScopeViolation: Requisição fora do escopo (a decisão `denied` foi auditada e
                nada foi enviado).
            TargetTimeout: O alvo não respondeu a tempo.
            TargetUnreachable: Não foi possível falar com o alvo.
            ExternalToolError: O proxy do ZAP não respondeu.
        """
        self._limiter.wait()
        self._gate.check()
        try:
            approved = approve(self._guard, request)
        except ScopeViolation as error:
            self._trail.decide(request, error.message)
            raise
        seq = self._trail.decide(request, None)
        started = self._clock.now()
        try:
            response = self._client.send(approved)
        except HarnessError as error:
            self._trail.finish(seq, request, status=None, error=error.code, ms=self._ms(started))
            raise
        self._trail.finish(seq, request, status=response.status, error=None, ms=self._ms(started))
        return response

    def _ms(self, started: datetime) -> int:
        return int((self._clock.now() - started).total_seconds() * 1000)
