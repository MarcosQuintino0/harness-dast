"""Comandos `hdast profile validate`, `profile approve` e `profile approval`.

`approve` é só da PESSOA (ADR 0037): recusa sem terminal interativo e com `--json`, mostra o
resumo dos blocos de proteção e exige que ela DIGITE o nome do produto. Não existe flag, arquivo
nem variável de ambiente que confirme no lugar dela. `approval` só lê e fica liberado ao agente.
"""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.scope_approval import ApprovalInfo, ApproveReport
from harness_dast.application.validate_profile import ProfileReport
from harness_dast.cli.approval_composition import build_scope_approvals
from harness_dast.cli.approval_prompt import TerminalApprovalPrompt
from harness_dast.cli.composition import build_validate_profile, products_dir_or_default
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.terminal import is_interactive

_PRODUCTS_DIR = typer.Option(
    "--products-dir",
    help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
    show_default=False,
)
_STATE_TEXT = {
    "approved": "APROVADO",
    "not_approved": "NÃO aprovado",
    "changed": "ALTERADO desde a aprovação (vale como não aprovado)",
    "invalid": "aprovação INVÁLIDA (vale como não aprovado)",
}


def _is_interactive() -> bool:
    return is_interactive()


def _yes_no(value: bool) -> str:
    return "sim" if value else "não"


def _approval_line(approval: ApprovalInfo) -> str:
    line = f"Aprovação do escopo: {_STATE_TEXT[approval.state]}"
    if approval.changed_blocks:
        line += f"; blocos alterados: {', '.join(approval.changed_blocks)}"
    return line


def _render(report: ProfileReport) -> str:
    accounts = ", ".join(f"{a.alias} ({a.role})" for a in report.accounts)
    windows = "; ".join(
        f"{','.join(w.days)} {w.start}-{w.end} {w.timezone} (aberta agora: {_yes_no(w.open_now)})"
        for w in report.windows
    )
    limits = report.limits
    lines = [
        f"Perfil do produto {report.product}: estrutura válida.",
        f"Ambiente: {report.environment_name} ({report.base_url_host})",
        f"Escopo: {report.allow_rules} regra(s) de permissão; negados: "
        f"{', '.join(report.deny_paths) or 'nenhum'}",
        f"Autenticação: {report.auth_type}; contas: {accounts}",
        f"Autorização: {report.authorization_reference}, válida até "
        f"{report.authorization_valid_until} "
        f"(vale agora: {_yes_no(report.authorization_valid_now)})",
        f"Janelas: {windows} (alguma aberta agora: {_yes_no(report.window_open_now)})",
        f"Limites: {limits.requests_per_second} req/s, {limits.max_duration_minutes} min, "
        f"{limits.zap_threads_per_host} thread(s) do ZAP por host",
        f"Limpeza configurada: {_yes_no(report.cleanup_configured)}",
        f"Verificado em: {report.checked_at}",
    ]
    lines.append(_approval_line(report.approval))
    if report.runnable:
        lines.append("Perfil pronto para executar agora (a aprovação do escopo é à parte).")
    else:
        lines.append(f"Ainda NÃO executável ({len(report.issues)} pendência(s)):")
        lines.extend(f"  - [{i.code}] {i.field}: {i.message}" for i in report.issues)
    return "\n".join(lines)


def _render_approve(report: ApproveReport) -> str:
    if report.already_approved:
        return (
            f"O escopo de {report.product} já estava aprovado ({report.approved_at}); nada mudou."
        )
    if not report.approved:
        return f"Aprovação de {report.product} cancelada; nada foi gravado."
    return f"Escopo de {report.product} APROVADO em {report.approved_at}."


def validate_command(
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
    """Valida o target.yml e informa se o perfil já pode ser executado agora."""
    state = get_state(ctx)
    report = build_validate_profile(products_dir).execute(product)
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render(report),
    )


def approve_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    products_dir: Annotated[Path | None, _PRODUCTS_DIR] = None,
) -> None:
    """Aprova os blocos de proteção do perfil; só uma pessoa, digitando no terminal."""
    state = get_state(ctx)
    root = products_dir_or_default(products_dir)
    use_case = build_scope_approvals(root, TerminalApprovalPrompt())
    # `--json` é recusado como a falta de terminal: aprovação não é para script nem agente.
    report = use_case.approve(product, interactive=_is_interactive() and not state.json_mode)
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render_approve(report),
    )


def approval_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    products_dir: Annotated[Path | None, _PRODUCTS_DIR] = None,
) -> None:
    """Diz se o escopo está aprovado, alterado desde a aprovação ou nunca aprovado (só lê)."""
    state = get_state(ctx)
    info = build_scope_approvals(products_dir_or_default(products_dir), TerminalApprovalPrompt())
    approval = info.status(product)
    emit(
        build_success({"product": product, **approval.model_dump(mode="json")}),
        json_mode=state.json_mode,
        human=f"{_approval_line(approval)}\n{approval.message}",
    )


def build_profile_app() -> typer.Typer:
    """Cria o grupo `hdast profile` com seus subcomandos."""
    profile_app = typer.Typer(help="Comandos do perfil de produto.")
    profile_app.command("validate")(validate_command)
    profile_app.command("approve")(approve_command)
    profile_app.command("approval")(approval_command)
    return profile_app
