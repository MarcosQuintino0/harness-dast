"""Comandos `hdast secret set|list|delete`: a PESSOA gere o cofre de credenciais (ADR 0030).

`set` e `delete` só funcionam em terminal interativo (stdin e stderr): o valor é digitado no
prompt oculto e nunca passa por argumento, variável de ambiente nem entrada redirecionada.
Sem terminal, recusam. `list` só mostra nomes e se existem; nenhum comando mostra valor ou
tamanho.
"""

import sys
from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.secret_admin import (
    SecretDeleteReport,
    SecretListReport,
    SecretWriteReport,
)
from harness_dast.cli.composition import build_secret_admin
from harness_dast.cli.output import build_success, emit, get_state

_PRODUCTS_DIR = typer.Option(
    "--products-dir",
    help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
    show_default=False,
)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


class TerminalSecretPrompt:
    """Prompt de terminal: valor oculto com confirmação, e remoção por nome digitado."""

    def read_value(self, name: str) -> str:
        """Lê o valor sem eco, duas vezes; pede de novo se as duas não coincidem."""
        return str(
            typer.prompt(
                f"Valor de {name} (não aparece enquanto você digita)",
                hide_input=True,
                confirmation_prompt="Repita o valor",
                err=True,
            )
        )

    def confirm_removal(self, name: str) -> bool:
        """Devolve `True` só se o texto digitado for exatamente `name`."""
        answer = typer.prompt(
            f"Digite '{name}' para REMOVER do cofre (outra coisa cancela)",
            default="",
            show_default=False,
            err=True,
        )
        return str(answer).strip() == name


def _render_write(report: SecretWriteReport) -> str:
    verb = "substituído" if report.replaced else "gravado"
    return f"Segredo {report.name} {verb} no cofre do sistema (o valor não é exibido)."


def _render_delete(report: SecretDeleteReport) -> str:
    if report.removed:
        return f"Segredo {report.name} removido do cofre."
    if not report.existed:
        return f"Segredo {report.name} não existe no cofre; nada a remover."
    return f"Remoção de {report.name} cancelada; nada foi alterado."


def _render_list(report: SecretListReport) -> str:
    if not report.entries:
        return f"{report.product}: o perfil não usa secret_ref: keyring:NOME."
    lines = [f"Segredos do cofre citados por {report.product}:"]
    for entry in report.entries:
        state = (
            "presente" if entry.present else "AUSENTE (rode: hdast secret set " + entry.name + ")"
        )
        lines.append(f"  {entry.name}: {state}; usado em {', '.join(entry.used_by)}")
    return "\n".join(lines)


def set_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="NOME de secret_ref: keyring:NOME.")],
    products_dir: Annotated[Path | None, _PRODUCTS_DIR] = None,
) -> int:
    """Grava um segredo no cofre; o valor é digitado no prompt oculto (só em terminal)."""
    state = get_state(ctx)
    admin = build_secret_admin(products_dir, state.secrets, TerminalSecretPrompt())
    report = admin.set_secret(name, interactive=_is_interactive())
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render_write(report),
    )
    return 0


def delete_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="NOME de secret_ref: keyring:NOME.")],
    products_dir: Annotated[Path | None, _PRODUCTS_DIR] = None,
) -> int:
    """Remove um segredo do cofre, depois de você digitar o nome (só em terminal)."""
    state = get_state(ctx)
    admin = build_secret_admin(products_dir, state.secrets, TerminalSecretPrompt())
    report = admin.delete_secret(name, interactive=_is_interactive())
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render_delete(report),
    )
    return 0


def list_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    products_dir: Annotated[Path | None, _PRODUCTS_DIR] = None,
) -> int:
    """Lista os segredos do cofre que o perfil cita e se existem (nunca o valor)."""
    state = get_state(ctx)
    admin = build_secret_admin(products_dir, state.secrets, TerminalSecretPrompt())
    report = admin.list_secrets(product)
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render_list(report),
    )
    return 0


def build_secret_app() -> typer.Typer:
    """Cria o grupo `hdast secret`."""
    app = typer.Typer(
        help="Cofre de credenciais do sistema: a pessoa grava, lista e remove segredos.",
        no_args_is_help=True,
    )
    app.command("set")(set_command)
    app.command("list")(list_command)
    app.command("delete")(delete_command)
    return app
