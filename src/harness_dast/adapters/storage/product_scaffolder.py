"""Criador de pastas de produto a partir do modelo `products/_template`.

Implementa a porta `ProductScaffolder`. Onde fica o modelo: `products/_template` na raiz do
repositório, localizado a partir deste arquivo (`default_template_dir`). Isso vale com
`uv run` e instalação editável (`uv sync`), que é o uso da V1. Uma instalação "wheel" não
carrega a pasta `products/`; nesse caso o erro orienta a rodar a partir do repositório.
"""

import re
import shutil
from pathlib import Path

from harness_dast.adapters.storage.product_paths import product_dir_path
from harness_dast.application.init_ports import ScaffoldedProduct
from harness_dast.domain.errors import ConfigError

PROFILE_FILE = "target.yml"
CLEANUP_DIR = "cleanup"
# O modelo traz um nome de produto de exemplo; a cópia passa a usar o nome da pasta, que é o
# que o carregador exige que o campo `product` seja.
_PRODUCT_LINE = re.compile(r"^product: meu-produto[ \t]*$", re.MULTILINE)


def default_template_dir() -> Path:
    """Caminho do modelo no repositório: `<raiz>/products/_template`."""
    return Path(__file__).resolve().parents[4] / "products" / "_template"


def _copy_template(
    template: Path,
    destination: Path,
    product: str,
    *,
    with_cleanup: bool,
    target_text: str | None,
) -> None:
    for source in sorted(template.rglob("*")):
        if source.is_symlink():
            continue
        if not with_cleanup and source.relative_to(template).parts[0] == CLEANUP_DIR:
            continue
        target = destination / source.relative_to(template)
        if source.is_dir():
            target.mkdir()
        elif source.name == PROFILE_FILE and source.parent == template and target_text is not None:
            target.write_bytes(target_text.encode("utf-8"))
        elif source.name == PROFILE_FILE and source.parent == template:
            text = source.read_text(encoding="utf-8")
            renamed, count = _PRODUCT_LINE.subn(f"product: {product}", text)
            if count != 1:
                raise ConfigError(
                    f"O {PROFILE_FILE} do modelo não tem uma única linha 'product: meu-produto'.",
                    hint="O modelo do repositório foi alterado; restaure products/_template.",
                )
            target.write_bytes(renamed.encode("utf-8"))
        elif source.is_file():
            shutil.copyfile(source, target)


class FileProductScaffolder:
    """Cria a pasta do produto copiando o modelo."""

    def __init__(self, products_dir: Path, template_dir: Path) -> None:
        """Cria o criador.

        Args:
            products_dir: Pasta de produtos (precisa existir).
            template_dir: Pasta do modelo a copiar.
        """
        self._products_dir = products_dir
        self._template_dir = template_dir

    def scaffold(
        self, product: str, *, with_cleanup: bool = False, target_text: str | None = None
    ) -> ScaffoldedProduct:
        """Cria a pasta do produto (veja `ProductScaffolder.scaffold`)."""
        destination = product_dir_path(self._products_dir, product)
        if not self._template_dir.is_dir():
            raise ConfigError(
                "O modelo de produto (products/_template) não foi encontrado.",
                hint="Rode o hdast a partir do repositório (uv run hdast ...).",
            )
        try:
            destination.mkdir()
        except FileExistsError:
            raise ConfigError(
                f"O produto {product} já existe em {self._products_dir}; nada foi alterado.",
                hint="Escolha outro nome ou edite os arquivos da pasta existente.",
            ) from None
        except OSError:
            raise ConfigError(
                "Não foi possível criar a pasta do produto.",
                hint="Confira a permissão de escrita em products_dir.",
            ) from None
        try:
            _copy_template(
                self._template_dir,
                destination,
                product,
                with_cleanup=with_cleanup,
                target_text=target_text,
            )
        except (OSError, ConfigError) as error:
            shutil.rmtree(destination, ignore_errors=True)
            if isinstance(error, ConfigError):
                raise
            raise ConfigError(
                "Falha ao copiar o modelo; a pasta parcial foi removida.",
                hint="Confira espaço em disco e permissões.",
            ) from None
        files = tuple(
            sorted(
                p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()
            )
        )
        return ScaffoldedProduct(directory=destination.as_posix(), files=files)
