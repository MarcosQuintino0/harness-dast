"""Comando de declaração humana de um achado existente."""

import sys
from typing import Annotated

import typer

from harness_dast.cli.human_confirmation_composition import build_human_confirmation
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.terminal import is_interactive


class TerminalConfirmationPrompt:
    """Coleta quem viu, o que viu e confirmação expressa no terminal."""

    def ask(self, fingerprint: str) -> tuple[str, str] | None:
        """Só aceita a declaração se a pessoa digitar o fingerprint completo."""
        typer.echo("Não inclua segredos ou dados pessoais na observação.", err=True)
        person = str(typer.prompt("Quem confirmou", default="", show_default=False, err=True))
        observation = str(typer.prompt("O que você viu", default="", show_default=False, err=True))
        answer = str(
            typer.prompt(
                f"Digite o fingerprint {fingerprint} para registrar (outra resposta cancela)",
                default="",
                show_default=False,
                err=True,
            )
        )
        return (person, observation) if answer == fingerprint else None


def acknowledge_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument()],
    run: Annotated[str, typer.Option("--run")],
    fingerprint: Annotated[str, typer.Option("--finding")],
) -> None:
    """Registra confirmação declarada por pessoa, em terminal interativo."""
    state = get_state(ctx)
    recorded = build_human_confirmation(TerminalConfirmationPrompt(), state.secrets).execute(
        product,
        run,
        fingerprint,
        interactive=is_interactive() and sys.stdout.isatty() and not state.json_mode,
    )
    emit(
        build_success({"recorded": recorded}),
        json_mode=False,
        human="Confirmação registrada." if recorded else "Confirmação cancelada; nada foi gravado.",
    )


def build_finding_app() -> typer.Typer:
    """Cria o grupo de comandos de achados."""
    app = typer.Typer(help="Comandos de achados.")
    app.command("acknowledge")(acknowledge_command)
    return app
