"""Leitor do OpenAPI de um produto (implementa a porta `SpecLoader`).

Resolve o caminho do arquivo por uma função injetada (a CLI passa a que garante que o arquivo
fica dentro da pasta do produto) e delega a leitura a `load_spec`. Assim este adaptador não
importa o adaptador de armazenamento.
"""

from collections.abc import Callable
from pathlib import Path

from harness_dast.adapters.openapi.loader import load_spec
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.profile import ProductProfile


class FileSpecLoader:
    """Carrega o OpenAPI apontado por `profile.openapi`."""

    def __init__(self, resolve: Callable[[str, str], Path]) -> None:
        """Cria o leitor.

        Args:
            resolve: Recebe (produto, caminho relativo) e devolve o caminho absoluto já
                conferido como interno à pasta do produto; levanta `ConfigError` se não for.
        """
        self._resolve = resolve

    def load(self, product: str, profile: ProductProfile) -> ApiSpec:
        """Carrega e normaliza o OpenAPI (veja `SpecLoader.load`)."""
        return load_spec(self._resolve(product, profile.openapi))
