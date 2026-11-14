"""Falsos em memória das portas da trava da pilha (ADR 0035), com comportamento."""

from pathlib import Path

from harness_dast.domain.errors import ConfigError


class InMemoryLockFile:
    """Implementa `StackLockFile` em memória.

    `content` é o texto do arquivo (`None`: não existe); o teste pode plantar qualquer texto
    (vazio, corrompido). `fail_release` faz apagar falhar, como um disco com problema.
    """

    def __init__(self, content: str | None = None) -> None:
        self.content = content
        self.fail_release = False
        self.removals = 0

    def location(self) -> Path:
        return Path("stack.lock")

    def create_exclusive(self, content: str) -> bool:
        if self.content is not None:
            return False
        self.content = content
        return True

    def read(self) -> str | None:
        return self.content

    def remove_if_unchanged(self, expected: str) -> bool:
        if self.fail_release:
            raise ConfigError("disco com problema")
        if self.content != expected:
            return False
        self.content = None
        self.removals += 1
        return True


class FakeProcesses:
    """Implementa `ProcessProbe`: este processo tem o PID dado e só os de `alive` vivem."""

    def __init__(self, pid: int = 4242, alive: set[int] | None = None) -> None:
        self._pid = pid
        self.alive = alive if alive is not None else set()

    def current_pid(self) -> int:
        return self._pid

    def is_alive(self, pid: int) -> bool:
        return pid in self.alive or pid == self._pid
