"""Comando `hdast version`."""

import typer

from harness_dast import __version__
from harness_dast.cli.output import build_success, emit, get_state


def emit_version(*, json_mode: bool, plain: bool = False) -> None:
    """Emite a versão instalada, com texto simples para a consulta do hook."""
    emit(
        build_success({"version": __version__}),
        json_mode=json_mode,
        human=__version__ if plain else None,
    )


def version_command(ctx: typer.Context) -> None:
    """Mostra a versão instalada do harness."""
    emit_version(json_mode=get_state(ctx).json_mode)
