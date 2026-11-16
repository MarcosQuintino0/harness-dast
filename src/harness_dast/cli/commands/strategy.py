"""Comandos locais de inspeção e migração de estratégia."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.strategy_composition import build_strategy

_DIR = typer.Option("--products-dir", show_default=False)


def validate_command(
    ctx: typer.Context, product: str, products_dir: Annotated[Path | None, _DIR] = None
) -> None:
    """Valida a estratégia sem tráfego."""
    data = build_strategy(products_dir).inspect(product)
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))


def diff_command(
    ctx: typer.Context, product: str, products_dir: Annotated[Path | None, _DIR] = None
) -> None:
    """Mostra a classificação da estratégia sem expor valores livres."""
    data = build_strategy(products_dir).diff(product)
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))


def migrate_command(
    ctx: typer.Context,
    product: str,
    output: Annotated[str, typer.Option("--output")] = "strategy.migrated.yml",
    products_dir: Annotated[Path | None, _DIR] = None,
) -> None:
    """Cria uma cópia neutra sem ativá-la."""
    data = build_strategy(products_dir).migrate(product, output)
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))


def build_strategy_app() -> typer.Typer:
    """Cria grupo de estratégia."""
    app = typer.Typer(help="Inspeção local de estratégia.")
    app.command("validate")(validate_command)
    app.command("diff")(diff_command)
    app.command("migrate")(migrate_command)
    return app
