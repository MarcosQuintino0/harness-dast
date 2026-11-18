"""Comando `hdast setup <produto>`: a PESSOA grava as senhas e aprova o escopo (ADR 0114).

Junta, só na ordem, os dois atos humanos que já existiam (`secret set` e `profile approve`) sem
juntar as decisões. Como eles, recusa sem terminal interativo e com `--json`: não existe flag,
arquivo nem variável que dispense a pessoa. O agente nunca o roda.
"""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.setup_product import SetupReport
from harness_dast.cli.approval_prompt import TerminalApprovalPrompt
from harness_dast.cli.commands.secret import TerminalSecretPrompt
from harness_dast.cli.composition import products_dir_or_default
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.setup_composition import build_setup_product
from harness_dast.cli.terminal import is_interactive


class TerminalNotifier:
    """Fala com a pessoa pelo stderr, como os demais prompts."""

    def say(self, text: str) -> None:
        """Escreve uma linha no stderr."""
        typer.echo(text, err=True)


def _is_interactive() -> bool:
    return is_interactive()


def _render(report: SetupReport) -> str:
    approval = report.approval
    if approval.already_approved:
        verdict = f"O escopo de {report.product} já estava aprovado ({approval.approved_at})."
    elif approval.approved:
        verdict = f"Escopo de {report.product} APROVADO em {approval.approved_at}."
    else:
        verdict = f"Aprovação de {report.product} cancelada; nenhuma aprovação foi gravada."
    lines = [verdict]
    if report.secrets_written:
        lines.append("Senhas gravadas no cofre: " + ", ".join(report.secrets_written))
        if not (approval.approved or approval.already_approved):
            lines.append(
                "Essas senhas continuam no cofre; remova com hdast secret delete se quiser."
            )
    if report.secrets_present:
        lines.append("Senhas que já estavam no cofre: " + ", ".join(report.secrets_present))
    if report.env_secrets:
        lines.append("Segredos que vêm do ambiente: " + ", ".join(report.env_secrets))
    return "\n".join(lines)


def setup_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Grava as senhas que faltam e aprova o escopo do produto; só uma pessoa, no terminal."""
    state = get_state(ctx)
    use_case = build_setup_product(
        products_dir_or_default(products_dir),
        state.secrets,
        secret_prompt=TerminalSecretPrompt(),
        approval_prompt=TerminalApprovalPrompt(pause=True),
        notifier=TerminalNotifier(),
    )
    # `--json` é recusado como a falta de terminal: o setup não é para script nem agente.
    report = use_case.run(product, interactive=_is_interactive() and not state.json_mode)
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render(report),
    )
