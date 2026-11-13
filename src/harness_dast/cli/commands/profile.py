"""Comando `hdast profile validate`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.validate_profile import ProfileReport
from harness_dast.cli.composition import build_validate_profile
from harness_dast.cli.output import build_success, emit, get_state


def _yes_no(value: bool) -> str:
    return "sim" if value else "não"


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
    if report.runnable:
        lines.append("Pronto para executar agora.")
    else:
        lines.append(f"Ainda NÃO executável ({len(report.issues)} pendência(s)):")
        lines.extend(f"  - [{i.code}] {i.field}: {i.message}" for i in report.issues)
    return "\n".join(lines)


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


def build_profile_app() -> typer.Typer:
    """Cria o grupo `hdast profile` com seus subcomandos."""
    profile_app = typer.Typer(help="Comandos do perfil de produto.")
    profile_app.command("validate")(validate_command)
    return profile_app
