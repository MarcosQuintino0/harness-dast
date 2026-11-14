"""Caso de uso da trava exclusiva por pilha (ADR 0035).

`hold` toma a trava e a solta sempre (sucesso, erro ou interrupção). A segunda execução na mesma
pilha falha fechada com `StackBusy`. Trava de processo morto (órfã) é retomada; trava de
processo vivo, nunca apagada; arquivo ilegível falha fechado. A decisão é do domínio
(`judge_lock`); aqui só se orquestra: relógio, processo e arquivo entram por porta.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import structlog

from harness_dast.application.ports import Clock, ProcessProbe, RandomSource, StackLockFile
from harness_dast.application.stack_models import StackLockInfo
from harness_dast.domain.errors import ConfigError, StackBusy
from harness_dast.domain.stack_lock import (
    LockHolder,
    LockVerdict,
    busy_message,
    describe_holder,
    judge_lock,
    parse_lock,
    render_lock,
    unreadable_message,
)

_log = structlog.get_logger()
_ID_BYTES = 6
_ATTEMPTS = 3
"""Tentativas de tomar a trava: a normal, a de depois de retomar órfã e uma de folga."""


class StackLockService:
    """Toma, solta e descreve a trava da pilha."""

    def __init__(
        self,
        *,
        store: StackLockFile,
        clock: Clock,
        processes: ProcessProbe,
        random: RandomSource,
    ) -> None:
        """Cria o caso de uso.

        Args:
            store: Arquivo de trava.
            clock: Relógio injetado.
            processes: Processo atual e "processo vivo?".
            random: Identificador da tomada.
        """
        self._store = store
        self._clock = clock
        self._processes = processes
        self._random = random

    @contextmanager
    def hold(self, command: str, product: str) -> Iterator[LockHolder]:
        """Toma a trava para o bloco e a solta ao sair, mesmo com erro ou interrupção.

        Args:
            command: Nome do comando que ocupa a pilha (vai na mensagem de quem é recusado).
            product: Produto da execução.

        Yields:
            O dono gravado no arquivo.

        Raises:
            StackBusy: Outra execução ocupa a pilha, ou a trava não pôde ser lida.
            ConfigError: Falha de escrita ou leitura do arquivo de trava.
        """
        holder = LockHolder(
            lock_id=self._random.token_hex(_ID_BYTES),
            command=command,
            product=product,
            pid=self._processes.current_pid(),
            started_at=self._clock.now(),
        )
        text = render_lock(holder)
        self._acquire(text)
        try:
            yield holder
        finally:
            self._release(text)

    def inspect(self) -> StackLockInfo | None:
        """Quem ocupa a pilha agora; `None` com a pilha livre.

        Raises:
            ConfigError: O arquivo existe, mas não pôde ser lido.
        """
        raw = self._store.read()
        if raw is None:
            return None
        holder = parse_lock(raw)
        verdict = judge_lock(holder, process_alive=self._alive(holder))
        if holder is None or verdict is LockVerdict.UNREADABLE:
            message, hint = unreadable_message(str(self._store.location()))
            return StackLockInfo(state="unreadable", message=f"{message} {hint}")
        now = self._clock.now()
        if verdict is LockVerdict.ORPHAN:
            message = (
                f"Trava órfã de {describe_holder(holder, now)}: o processo morreu sem soltar. "
                "A próxima execução a retoma."
            )
        else:
            message = busy_message(holder, now)[0]
        return StackLockInfo(
            state="orphan" if verdict is LockVerdict.ORPHAN else "held",
            command=holder.command,
            product=holder.product,
            lock_id=holder.lock_id,
            pid=holder.pid,
            started_at=holder.started_at.isoformat(),
            message=message,
        )

    def _acquire(self, text: str) -> None:
        for _ in range(_ATTEMPTS):
            if self._store.create_exclusive(text):
                return
            self._settle_existing()
        raise StackBusy(
            "Outra execução tomou a pilha no mesmo instante.",
            hint="Espere um pouco, confira com hdast stack status e tente de novo.",
        )

    def _settle_existing(self) -> None:
        """Olha a trava que já existe: recusa se for de dono vivo, retoma se for órfã."""
        raw = self._store.read()
        if raw is None:
            return  # sumiu entre a criação e a leitura: a próxima tentativa a cria
        holder = parse_lock(raw)
        verdict = judge_lock(holder, process_alive=self._alive(holder))
        if holder is None or verdict is LockVerdict.UNREADABLE:
            message, hint = unreadable_message(str(self._store.location()))
            raise StackBusy(message, hint=hint)
        if verdict is LockVerdict.HELD:
            message, hint = busy_message(holder, self._clock.now())
            raise StackBusy(message, hint=hint)
        _log.warning(
            "stack_lock_orphan_taken_over",
            lock_id=holder.lock_id,
            command=holder.command,
            pid=holder.pid,
        )
        # Só apaga se ainda for a MESMA trava órfã: outra execução pode tê-la retomado antes.
        self._store.remove_if_unchanged(raw)

    def _alive(self, holder: LockHolder | None) -> bool:
        return holder is not None and self._processes.is_alive(holder.pid)

    def _release(self, text: str) -> None:
        try:
            self._store.remove_if_unchanged(text)
        except ConfigError as error:
            # Soltar nunca mascara o erro (ou o resultado) do bloco; a trava que sobrar vira
            # órfã quando este processo terminar.
            _log.warning("stack_lock_release_failed", reason=error.message)
