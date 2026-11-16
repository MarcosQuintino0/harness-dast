"""Prévia local, sem tráfego."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.strategy_composition import build_strategy
from harness_dast.domain.errors import ConfigError


def plan_command(
    ctx: typer.Context,
    product: str,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    products_dir: Annotated[Path | None, typer.Option("--products-dir")] = None,
) -> None:
    """Compila prévia de estratégia sem tocar alvo ou ZAP."""
    if not dry_run:
        raise ConfigError("A prévia exige --dry-run.")
    data = build_strategy(products_dir).compile(product)
    emit(build_success(data), json_mode=get_state(ctx).json_mode, human=str(data))
