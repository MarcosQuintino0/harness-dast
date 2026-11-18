"""Leitor dos padrões mínimos da CLI gravados no cabeçalho do `target.yml` (ADR 0114).

Implementa a porta `AppliedDefaultsReader`. Só traduz arquivo em texto; quem reconhece as linhas
é o domínio (`read_default_notes`). Não valida o perfil: isso é do `ProfileRepository`.
"""

from pathlib import Path

from harness_dast.adapters.storage.product_paths import product_dir_path
from harness_dast.adapters.storage.profile_repository import PROFILE_FILE, read_profile_text
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter_defaults import read_default_notes


class FileAppliedDefaults:
    """Lê `<produtos>/<produto>/target.yml` atrás dos padrões aplicados pela carta."""

    def __init__(self, products_dir: Path) -> None:
        """Cria o leitor.

        Args:
            products_dir: Pasta que contém uma subpasta por produto.
        """
        self._products_dir = products_dir

    def read(self, product: str) -> tuple[str, ...]:
        """Devolve `campo = valor` de cada padrão aplicado; vazio se o perfil não os tem."""
        target = product_dir_path(self._products_dir, product) / PROFILE_FILE
        if not target.is_file():
            raise ConfigError(
                f"O produto {product} não tem {PROFILE_FILE}.",
                hint="Crie o produto com hdast init.",
            )
        return read_default_notes(read_profile_text(target))
