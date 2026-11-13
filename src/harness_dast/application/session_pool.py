"""Sessões de conta reaproveitadas: um login por conta por execução.

`SessionPool` abre cada conta uma única vez, sob demanda. Uma conta cuja abertura falhou NÃO é
tentada de novo (cada tentativa gastaria o orçamento de login): a mesma falha é repetida.
"""

from collections.abc import Callable

from harness_dast.application.account_session import AccountSession
from harness_dast.domain.errors import HarnessError


class SessionPool:
    """Abre cada conta uma vez e devolve a mesma sessão depois."""

    def __init__(self, make_session: Callable[[str], AccountSession]) -> None:
        """Cria o conjunto.

        Args:
            make_session: Cria a sessão (ainda fechada) de um apelido de conta.
        """
        self._make = make_session
        self._open: dict[str, AccountSession] = {}
        self._failed: dict[str, HarnessError] = {}

    def get(self, alias: str) -> AccountSession:
        """Sessão aberta da conta (segredos, CSRF e login feitos uma vez).

        Raises:
            PreflightError: A abertura falhou (agora ou numa chamada anterior).
            ScopeViolation: Fora do escopo, janela fechada ou prazo esgotado.
        """
        if alias in self._failed:
            raise self._failed[alias]
        if alias not in self._open:
            session = self._make(alias)
            try:
                session.open()
            except HarnessError as error:
                self._failed[alias] = error
                raise
            self._open[alias] = session
        return self._open[alias]
