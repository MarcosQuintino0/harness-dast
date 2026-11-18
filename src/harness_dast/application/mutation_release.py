"""Liberação humana de intenção pendente, sem acesso ao alvo."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.knowledge_mutation import PendingMutation


class MutationReleaseStore(Protocol):
    """Lê e arquiva intenções, mantendo o desfecho de liberação humana."""

    def read_pending(self, key: str) -> PendingMutation:
        """Valida só a entrada pedida; ausente, inválida ou corrompida levanta `ConfigError`."""
        ...

    def release(self, key: str, released_at: datetime) -> None:
        """Arquiva intenção e registra o instante da liberação."""
        ...


def release_mutation(
    store: MutationReleaseStore,
    key: str,
    *,
    interactive: bool,
    confirm: Callable[[str], bool],
    now: Callable[[], datetime],
) -> bool:
    """Exige terminal e confirmação expressa após conferir a intenção; False cancela."""
    require_interactive(interactive)
    store.read_pending(key)
    if not confirm(key):
        return False
    store.release(key, now())
    return True


def require_interactive(interactive: bool) -> None:
    """Recusa liberação fora de terminal antes de obter qualquer trava ou confirmação."""
    if not interactive:
        raise ConfigError(
            "Liberação exige terminal interativo, sem --json.",
            hint="Peça a uma pessoa para conferir o alvo e executar o comando no terminal.",
        )
