"""Comando `hdast init`."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from harness_dast.application.ports import ScaffoldedProduct
from harness_dast.cli.composition import build_init_product
from harness_dast.cli.output import build_success, emit, get_state


def _render(product: str, result: ScaffoldedProduct) -> str:
    files = "\n".join(f"  - {name}" for name in result.files)
    return (
        f"Produto {product} criado em {result.directory}\n"
        f"Arquivos:\n{files}\n"
        "Próximos passos: preencha o target.yml (escopo, limites e autorização vêm da "
        "autorização formal) e rode: hdast profile validate " + product
    )


def init_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug, ex.: meu-produto).")],
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Cria a pasta do produto a partir do modelo, sem sobrescrever nada."""
    state = get_state(ctx)
    result = build_init_product(products_dir).execute(product)
    data: dict[str, JsonValue] = {
        "product": product,
        "directory": result.directory,
        "files": list(result.files),
    }
    emit(build_success(data), json_mode=state.json_mode, human=_render(product, result))
