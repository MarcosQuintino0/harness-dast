"""Arquivo de trava exclusiva da pilha (implementa `StackLockFile`, ADR 0035).

Fica em `<pasta de estado>/stack.lock`, ao lado de `stack.json` e fora de `runs/`: a pasta de
estado (`HDAST_STATE_DIR`) é o que identifica a pilha gerenciada.

Criação exclusiva e atômica: o conteúdo é gravado num arquivo temporário e publicado com
`os.link` para o nome final. `os.link` falha se o nome já existe e o arquivo nasce completo,
então nenhum leitor vê uma trava vazia ou pela metade (um `O_EXCL` seguido de escrita deixaria
essa janela). Apagar a trava só acontece sob um segundo arquivo de exclusão (`stack.lock.guard`)
e depois de reler o conteúdo, para que quem retoma uma trava órfã nunca apague a trava nova de
outra execução. Um `guard` mais velho que `GUARD_STALE_SECONDS` é de quem morreu no meio e é
descartado.
"""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from harness_dast.application.ports import Clock
from harness_dast.domain.errors import ConfigError

LOCK_FILE_NAME = "stack.lock"
GUARD_FILE_NAME = "stack.lock.guard"
GUARD_STALE_SECONDS = 30


class FileStackLock:
    """Guarda a trava em `<pasta>/stack.lock`."""

    def __init__(self, directory: Path, clock: Clock) -> None:
        """Cria o armazém (nada é criado até a primeira tomada).

        Args:
            directory: Pasta de estado.
            clock: Relógio, para descartar o `guard` abandonado.
        """
        self._directory = directory
        self._clock = clock

    def location(self) -> Path:
        """Caminho do arquivo de trava."""
        return self._directory / LOCK_FILE_NAME

    def create_exclusive(self, content: str) -> bool:
        """Cria a trava com o conteúdo completo; `False` se ela já existe."""
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self._directory, prefix=f".{LOCK_FILE_NAME}.", suffix=".tmp"
            )
        except OSError:
            raise _write_error() from None
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self.location())
            except FileExistsError:
                created = False
            else:
                created = True
        except OSError:
            raise _write_error() from None
        finally:
            temporary.unlink(missing_ok=True)
        return created

    def read(self) -> str | None:
        """Texto da trava; `None` se não existe. Bytes inválidos viram texto inválido."""
        try:
            return self.location().read_bytes().decode("utf-8", errors="replace")
        except FileNotFoundError:
            return None
        except OSError:
            raise ConfigError(
                f"Não foi possível ler o arquivo de trava da pilha ({self.location()}).",
                hint="Confira a permissão da pasta de estado (HDAST_STATE_DIR) e tente de novo.",
            ) from None

    def remove_if_unchanged(self, expected: str) -> bool:
        """Apaga a trava se o conteúdo ainda for `expected`, sob o arquivo de exclusão."""
        if not self._enter_guard():
            return False
        try:
            if self.read() != expected:
                return False
            try:
                self.location().unlink()
            except FileNotFoundError:
                return False
            except OSError:
                raise _write_error() from None
            return True
        finally:
            self._guard_path().unlink(missing_ok=True)

    def _guard_path(self) -> Path:
        return self._directory / GUARD_FILE_NAME

    def _enter_guard(self) -> bool:
        guard = self._guard_path()
        for _ in range(2):
            try:
                descriptor = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                if not self._discard_stale_guard(guard):
                    return False
                continue
            except OSError:
                raise _write_error() from None
            os.close(descriptor)
            return True
        return False

    def _discard_stale_guard(self, guard: Path) -> bool:
        try:
            modified = datetime.fromtimestamp(guard.stat().st_mtime, tz=UTC)
        except OSError:
            return True  # sumiu agora: tente criar de novo
        if (self._clock.now() - modified).total_seconds() <= GUARD_STALE_SECONDS:
            return False
        try:
            guard.unlink(missing_ok=True)
        except OSError:
            return False
        return True


def _write_error() -> ConfigError:
    return ConfigError(
        "Não foi possível gravar o arquivo de trava da pilha.",
        hint="Confira HDAST_STATE_DIR, o espaço em disco e a permissão de escrita.",
    )
