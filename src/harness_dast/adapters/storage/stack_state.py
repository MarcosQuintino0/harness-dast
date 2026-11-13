"""Estado da pilha gerenciada em um arquivo por pessoa usuária (implementa `StackStateStore`).

Onde fica: `HDAST_STATE_DIR`; senão, no Windows `%LOCALAPPDATA%/hdast`; senão
`$XDG_STATE_HOME/hdast` ou `~/.local/state/hdast`. Nunca dentro do repositório nem de `runs/`.

Por que um arquivo: a chave da API do ZAP é sorteada por `stack up` e os comandos seguintes
(`preflight`, `probe`, `stop`) rodam em outros processos. O arquivo guarda também as senhas
descartáveis do alvo de laboratório. Proteção: gravado por arquivo temporário com modo 0600 e
pasta 0700 (POSIX). No Windows o modo é ignorado; vale a ACL herdada de `%LOCALAPPDATA%`,
que na instalação padrão só dá acesso à própria pessoa, ao sistema e aos administradores.
O arquivo não é cifrado: proteja a conta do sistema operacional.

Também cria, por pilha, as pastas de política e de auditoria do proxy
(`<estado>/stacks/<run_id>/{policy,audit}`): uma por execução, para que o `KILL` de uma pilha
nunca valha para a seguinte e a auditoria de cada uma fique separada.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from harness_dast.application.stack_models import StackDirectories, StackState
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import RunId

STATE_FILE_NAME = "stack.json"
STATE_DIR_ENV = "HDAST_STATE_DIR"
_DIR_MODE = 0o700
_FILE_MODE = 0o600


def default_state_dir(environ: Mapping[str, str], *, windows: bool | None = None) -> Path:
    """Pasta de estado da pessoa usuária (veja o docstring do módulo)."""
    explicit = environ.get(STATE_DIR_ENV)
    if explicit:
        return Path(explicit)
    on_windows = sys.platform == "win32" if windows is None else windows
    if on_windows and environ.get("LOCALAPPDATA"):
        return Path(environ["LOCALAPPDATA"]) / "hdast"
    base = environ.get("XDG_STATE_HOME")
    return (Path(base) if base else Path.home() / ".local" / "state") / "hdast"


class FileStackStateStore:
    """Guarda o estado em `<pasta>/stack.json`."""

    def __init__(self, directory: Path) -> None:
        """Cria o armazém (nada é criado até o primeiro `save`).

        Args:
            directory: Pasta de estado.
        """
        self._directory = directory

    def location(self) -> Path:
        """Caminho do arquivo de estado."""
        return self._directory / STATE_FILE_NAME

    def load(self) -> StackState | None:
        """Lê o estado; `None` se o arquivo não existe."""
        path = self.location()
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            raise _read_error(path) from None
        try:
            return StackState.model_validate_json(raw)
        except ValidationError:
            raise _read_error(path) from None

    def save(self, state: StackState) -> None:
        """Grava o estado de forma atômica com modo 0600."""
        self._ensure_dir(self._directory)
        path = self.location()
        temporary = path.with_name(f".{STATE_FILE_NAME}.tmp")
        data = (state.model_dump_json(indent=2) + "\n").encode("utf-8")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError:
            raise _write_error() from None

    def clear(self) -> None:
        """Apaga o arquivo de estado se existir."""
        try:
            self.location().unlink(missing_ok=True)
        except OSError:
            raise _write_error() from None

    def directories_for(self, run_id: str) -> StackDirectories:
        """Cria `<estado>/stacks/<run_id>/policy` e `.../audit`."""
        valid = RunId(value=run_id)
        base = self._directory / "stacks" / valid.value
        policy, audit = base / "policy", base / "audit"
        for folder in (policy, audit):
            self._ensure_dir(folder)
        return StackDirectories(policy_dir=policy, audit_dir=audit)

    @staticmethod
    def _ensure_dir(folder: Path) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform != "win32":
                folder.chmod(_DIR_MODE)
        except OSError:
            raise _write_error() from None


def _read_error(path: Path) -> ConfigError:
    return ConfigError(
        f"O arquivo de estado da pilha ({path}) está ilegível ou inválido.",
        hint="Rode hdast stack down; se persistir, apague o arquivo e derrube os contêineres "
        "com docker compose -p hdast down.",
    )


def _write_error() -> ConfigError:
    return ConfigError(
        "Não foi possível gravar o estado da pilha.",
        hint="Confira HDAST_STATE_DIR, o espaço em disco e a permissão de escrita.",
    )
