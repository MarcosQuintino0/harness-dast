"""Comando `hdast version`."""

import typer

from harness_dast import __version__
from harness_dast.cli.output import build_success, emit, get_state


def version_command(ctx: typer.Context) -> None:
    """Mostra a versão instalada do harness."""
    state = get_state(ctx)
    emit(build_success({"version": __version__}), json_mode=state.json_mode)
