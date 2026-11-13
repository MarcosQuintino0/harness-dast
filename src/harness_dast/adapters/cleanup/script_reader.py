"""Leitor do script de limpeza do produto (implementa `CleanupScripts`).

Só LÊ: o script é de autoria humana e nada neste pacote o escreve ou altera. O caminho vem do
perfil e é resolvido por uma função injetada que garante que o arquivo fica dentro da pasta do
produto.
"""

from collections.abc import Callable
from pathlib import Path

from harness_dast.domain.cleanup_gate import MAX_SCRIPT_BYTES
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile


class FileCleanupScripts:
    """Lê o script apontado por `cleanup.script`."""

    def __init__(self, resolve: Callable[[str, str], Path]) -> None:
        """Cria o leitor.

        Args:
            resolve: Função (produto, caminho relativo) -> caminho absoluto dentro da pasta do
                produto; levanta `ConfigError` se o caminho sair dela.
        """
        self._resolve = resolve

    def read(self, product: str, profile: ProductProfile) -> bytes:
        """Lê até `MAX_SCRIPT_BYTES + 1` bytes do script."""
        if profile.cleanup is None:
            raise ConfigError("O perfil não tem o bloco cleanup.", hint="Adicione-o ao target.yml.")
        target = self._resolve(product, profile.cleanup.script)
        try:
            with target.open("rb") as handle:
                return handle.read(MAX_SCRIPT_BYTES + 1)
        except OSError:
            raise ConfigError(
                "Não foi possível ler o script de limpeza.",
                hint=(
                    "Confira se cleanup.script existe e tem permissão de leitura. O script é "
                    "escrito por uma pessoa do time do produto; a CLI não o cria."
                ),
            ) from None
