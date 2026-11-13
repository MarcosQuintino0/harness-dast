"""Leitura da trava de emergência: o arquivo `KILL` ao lado da política do proxy."""

from pathlib import Path

from harness_dast.adapters.scope_proxy.policy import KILL_FLAG_NAME


class FileKillSwitch:
    """Diz se `hdast stop` criou o arquivo `KILL` (implementa `KillSwitch`)."""

    def __init__(self, policy_dir: Path | None) -> None:
        """Cria a leitura.

        Args:
            policy_dir: Pasta da política do proxy; `None` (sem pilha conhecida) nunca aciona.
        """
        self._flag = None if policy_dir is None else policy_dir / KILL_FLAG_NAME

    def engaged(self) -> bool:
        """Se o arquivo `KILL` existe agora."""
        return self._flag is not None and self._flag.exists()
