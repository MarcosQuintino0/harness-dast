"""Grava o rascunho da tabela "quem pode o quê" na pasta do produto (implementa `AuthzDraftWriter`).

Só cria o arquivo fixo `authz-matrix.draft.yml`: abre em modo exclusivo, então um arquivo que
já existe (inclusive um link para o `target.yml`) nunca é sobrescrito. O carregador do perfil
não lê este arquivo.
"""

from pathlib import Path

from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.domain.authz.matrix_draft import DRAFT_FILE
from harness_dast.domain.errors import ConfigError


class FileAuthzDraftWriter:
    """Escreve o rascunho no sistema de arquivos."""

    def __init__(self, products_dir: Path) -> None:
        """Cria o gravador.

        Args:
            products_dir: Pasta que contém uma subpasta por produto.
        """
        self._products_dir = products_dir

    def write_draft(self, product: str, text: str) -> str:
        """Cria `authz-matrix.draft.yml` (veja `AuthzDraftWriter.write_draft`)."""
        path = resolve_product_file(self._products_dir, product, DRAFT_FILE)
        if not path.parent.is_dir():
            raise ConfigError(
                "A pasta do produto não existe.", hint="Crie o produto com: hdast init <produto>."
            )
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            raise ConfigError(
                f"Já existe {DRAFT_FILE} na pasta do produto; ele não é sobrescrito.",
                hint="Leve o que serve ao target.yml e apague o rascunho, ou renomeie-o.",
            ) from None
        except OSError:
            raise ConfigError(
                f"Não foi possível gravar {DRAFT_FILE}.",
                hint="Confira a permissão de escrita da pasta do produto.",
            ) from None
        return str(path)
