"""Criador de pastas de produto a partir do modelo `products/_template`.

Implementa a porta `ProductScaffolder`. Onde fica o modelo (`default_template_dir`): no clone,
`products/_template` na raiz do repositório; na instalação pelo wheel (plugin, ADR 0119), a cópia
empacotada em `harness_dast/product_template`, que um teste de contrato mantém igual à do clone.
"""

import os
import re
import shutil
from pathlib import Path

from harness_dast.adapters.storage.product_paths import product_dir_path
from harness_dast.application.init_ports import ScaffoldedProduct
from harness_dast.domain.errors import ConfigError

PROFILE_FILE = "target.yml"
CLEANUP_DIR = "cleanup"
# O que faz da pasta um perfil: se algum existir, o produto já foi criado e nada é sobrescrito. Uma
# pasta só com outros arquivos (o diário do agente, por exemplo) é aceita e fica intacta.
PROFILE_ENTRIES = (PROFILE_FILE, "data-rules.yml", "flows.yml", CLEANUP_DIR)
# O modelo traz um nome de produto de exemplo; a cópia passa a usar o nome da pasta, que é o
# que o carregador exige que o campo `product` seja.
_PRODUCT_LINE = re.compile(r"^product: meu-produto[ \t]*$", re.MULTILINE)


def default_template_dir(package: Path | None = None) -> Path:
    """Caminho do modelo: `<raiz>/products/_template` no clone, ou o do pacote instalado."""
    package = Path(__file__).resolve().parents[2] if package is None else package
    in_clone = package.parent.parent / "products" / "_template"
    if package.parent.name == "src" and in_clone.is_dir():
        return in_clone
    return package / "product_template"


def _keeps_existing(source: Path, target: Path) -> bool:
    """Diz se `target` já existe e fica como está; recusa se o tipo não bate com o do modelo."""
    if not os.path.lexists(target):
        return False
    same_kind = source.is_file() == target.is_file() and source.is_dir() == target.is_dir()
    if target.is_symlink() or not same_kind:
        raise ConfigError(
            f"Já existe {target.name} na pasta do produto e não é do mesmo tipo que o do modelo.",
            hint="Renomeie ou remova esse item e rode de novo.",
        )
    return True


def _copy_template(
    template: Path,
    destination: Path,
    product: str,
    *,
    with_cleanup: bool,
    target_text: str | None,
    created: list[Path],
) -> None:
    for source in sorted(template.rglob("*")):
        if source.is_symlink():
            continue
        if not with_cleanup and source.relative_to(template).parts[0] == CLEANUP_DIR:
            continue
        target = destination / source.relative_to(template)
        if _keeps_existing(source, target):
            continue
        created.append(target)
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
        """Cria a pasta do produto (veja `ProductScaffolder.scaffold`).

        Uma pasta que já existe e não tem nenhum arquivo do perfil (`target.yml`, `data-rules.yml`,
        `flows.yml`, `cleanup/`) é aceita: só os arquivos do modelo que faltam são criados e o que
        já estava lá fica intacto. Com qualquer arquivo do perfil, recusa e não altera nada.
        """
        destination = product_dir_path(self._products_dir, product)
        if not self._template_dir.is_dir():
            raise ConfigError(
                "O modelo de produto (products/_template) não foi encontrado.",
                hint="Rode o hdast a partir do repositório (uv run hdast ...).",
            )
        new_folder = _open_destination(destination, product, self._products_dir)
        created: list[Path] = []
        try:
            _copy_template(
                self._template_dir,
                destination,
                product,
                with_cleanup=with_cleanup,
                target_text=target_text,
                created=created,
            )
        except (OSError, ConfigError) as error:
            _undo(destination, created, whole_folder=new_folder)
            if isinstance(error, ConfigError):
                raise
            raise ConfigError(
                "Falha ao copiar o modelo; a parte criada (pasta parcial) foi removida.",
                hint="Confira espaço em disco e permissões.",
            ) from None
        files = tuple(sorted(p.relative_to(destination).as_posix() for p in created if p.is_file()))
        return ScaffoldedProduct(directory=destination.as_posix(), files=files)


def _open_destination(destination: Path, product: str, products_dir: Path) -> bool:
    """Cria a pasta ou aceita uma sem perfil; devolve se ela foi criada agora."""
    try:
        destination.mkdir()
    except FileExistsError:
        entries = (destination / name for name in PROFILE_ENTRIES)
        if (
            destination.is_symlink()
            or not destination.is_dir()
            or any(os.path.lexists(entry) for entry in entries)
        ):
            raise ConfigError(
                f"O produto {product} já existe em {products_dir}; nada foi alterado.",
                hint="Escolha outro nome ou edite os arquivos da pasta existente.",
            ) from None
        return False
    except OSError:
        raise ConfigError(
            "Não foi possível criar a pasta do produto.",
            hint="Confira a permissão de escrita em products_dir.",
        ) from None
    return True


def _undo(destination: Path, created: list[Path], *, whole_folder: bool) -> None:
    # Numa pasta que já existia, remove só o que esta chamada criou: o resto não é dela.
    if whole_folder:
        shutil.rmtree(destination, ignore_errors=True)
        return
    for path in reversed(created):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
