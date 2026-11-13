"""Orçamento de logins: nunca mais que `auth.login_limit.max_per_minute` por minuto.

Alvos reais limitam o login por origem e contam também as tentativas erradas (o piloto aceita
5 por minuto). Estourar o limite trava as contas de teste e distorce o resultado, então todo
POST de login (primeiro login, novo login após token vencido, repetição após 429, e a
operação de login do OpenAPI) passa por `acquire` ANTES de sair. O orçamento é uma janela
deslizante de 60 s (mais uma folga de 1 s) e espera, com o `Sleeper` injetado, quando está
cheio; não falha.
"""

from collections import deque
from typing import Final
from urllib.parse import urlsplit

from harness_dast.application.ports import Clock, Sleeper
from harness_dast.domain.auth import LoginLimit
from harness_dast.domain.http_messages import HttpRequest

WINDOW_SECONDS: Final = 60.0
SAFETY_MARGIN_SECONDS: Final = 1.0
"""Folga somada à janela: entre reservar a vaga e o pedido chegar ao alvo passam o ritmo (até 0,2 s
a 5 req/s) e a fila do proxy, e o alvo conta pela hora de chegada, não pela da reserva."""


def is_login_request(request: HttpRequest, login_path: str | None) -> bool:
    """Diz se a requisição é o POST de login do perfil."""
    if login_path is None or request.method != "POST":
        return False
    return urlsplit(request.url).path.rstrip("/") == login_path.rstrip("/")


class LoginBudget:
    """Janela deslizante de logins, com relógio e espera injetados."""

    def __init__(self, limit: LoginLimit | None, clock: Clock, sleeper: Sleeper) -> None:
        """Cria o orçamento.

        Args:
            limit: Taxa declarada no perfil; `None` não limita (o perfil não declarou).
            clock: Relógio injetado.
            sleeper: Espera injetada.
        """
        self._max = limit.max_per_minute if limit is not None else None
        self._window = WINDOW_SECONDS + SAFETY_MARGIN_SECONDS
        self._clock = clock
        self._sleeper = sleeper
        self._sent: deque[float] = deque()

    def acquire(self) -> None:
        """Reserva uma vaga de login, esperando se o minuto já está cheio."""
        if self._max is None:
            return
        while True:
            now = self._clock.now().timestamp()
            self._expire(now)
            if len(self._sent) < self._max:
                self._sent.append(now)
                return
            self._sleeper.sleep(self._window - (now - self._sent[0]))

    def _expire(self, now: float) -> None:
        while self._sent and now - self._sent[0] >= self._window:
            self._sent.popleft()
