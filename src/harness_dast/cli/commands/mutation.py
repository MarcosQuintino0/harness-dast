"""Inspeção de pendências e liberação exclusiva por pessoa."""

import os
import sys
from typing import Annotated

import typer
from pydantic import JsonValue, TypeAdapter

from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.mutation_release import release_mutation, require_interactive
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.cli.terminal import is_interactive


def _journal() -> FileMutationJournal:
    return FileMutationJournal(default_state_dir(os.environ) / "mutations")


def list_command(ctx: typer.Context) -> None:
    """Lista pendências sem mostrar snapshots ou corpos."""
    entries = _journal().list_pending()
    data = TypeAdapter(dict[str, JsonValue]).validate_python(
        {"pending": [entry.model_dump(mode="json") for entry in entries]}
    )
    human = "\n".join(str(entry.model_dump(mode="json")) for entry in entries)
    emit(
        build_success(data),
        json_mode=get_state(ctx).json_mode,
        human=human or "Nenhuma mutação pendente.",
    )


def _confirm(key: str) -> bool:
    answer = typer.prompt(
        f"Após conferir o alvo, digite {key} para liberar (outra resposta cancela)",
        default="",
        show_default=False,
        err=True,
    )
    return str(answer) == key


def release_command(ctx: typer.Context, mutation_id: Annotated[str, typer.Argument()]) -> None:
    """Registra conferência humana e libera uma intenção pendente."""
    state = get_state(ctx)
    interactive = is_interactive() and sys.stdout.isatty() and not state.json_mode
    require_interactive(interactive)
    with hold_stack("mutation release", "-"):
        released = release_mutation(
            _journal(),
            mutation_id,
            interactive=interactive,
            confirm=_confirm,
            now=SystemClock().now,
        )
    emit(
        build_success({"released": released}),
        json_mode=False,
        human="Mutação liberada." if released else "Liberação cancelada; nada foi gravado.",
    )


def build_mutation_app() -> typer.Typer:
    """Cria o grupo de comandos de mutação."""
    app = typer.Typer(help="Inspeciona intenções de mutação pendentes.")
    app.command("list")(list_command)
    app.command("release")(release_command)
    return app
