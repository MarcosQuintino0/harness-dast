"""Portas consumidas pela capacidade doctor; assinaturas e docstrings preservadas."""

from pathlib import Path
from typing import Protocol


class HostInspector(Protocol):
    """Olhos do `doctor` sobre a máquina: Docker, imagens, portas, pastas e ferramentas.

    Só lê. Nenhum método toca o alvo, sobe contêiner ou altera arquivo.
    """

    def docker_version(self) -> str:
        """Versão do servidor Docker que respondeu.

        Raises:
            ExternalToolError: Docker ausente, parado ou sem resposta no prazo.
        """
        ...

    def port_is_free(self, port: int) -> bool:
        """Diz se a porta TCP de 127.0.0.1 está livre para publicar."""
        ...

    def uv_version(self) -> str | None:
        """Versão do `uv` no PATH, ou `None` se não está instalado."""
        ...

    def directory_exists(self, path: Path) -> bool:
        """Diz se `path` existe e é uma pasta."""
        ...
