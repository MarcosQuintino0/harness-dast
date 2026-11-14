"""Montagem da trava exclusiva por pilha (ADR 0035) sobre a pasta de estado."""

import os
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext

from harness_dast.adapters.storage.stack_lock import FileStackLock
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_process import SystemProcessProbe
from harness_dast.adapters.system_random import SystemRandom
from harness_dast.application.stack_lock import StackLockService
from harness_dast.domain.stack_lock import LockHolder


def open_stack_lock(environ: Mapping[str, str] | None = None) -> StackLockService:
    """Trava da pilha da pasta de estado da pessoa usuária (`HDAST_STATE_DIR` e padrões)."""
    clock = SystemClock()
    directory = default_state_dir(os.environ if environ is None else environ)
    return StackLockService(
        store=FileStackLock(directory, clock),
        clock=clock,
        processes=SystemProcessProbe(),
        random=SystemRandom(),
    )


def hold_stack(
    command: str, product: str, *, needed: bool = True
) -> AbstractContextManager[LockHolder | None]:
    """Toma a trava da pilha para o bloco `with`; com `needed=False`, não faz nada.

    `needed=False` serve às simulações (`--dry-run`) que não tocam o ZAP nem o alvo.

    Raises:
        StackBusy: (ao entrar no bloco) outra execução ocupa a pilha.
    """
    if not needed:
        return nullcontext()
    return open_stack_lock().hold(command, product)
