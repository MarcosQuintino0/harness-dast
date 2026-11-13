"""Comandos `hdast stack up|status|down` e `hdast stop` (pilha de contêineres e trava)."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.stack import DEFAULT_UP_TIMEOUT_SECONDS, StackUpRequest
from harness_dast.application.stack_models import StackReport, StopReport
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.stack_composition import (
    build_stack_manager,
    open_zap_stopper,
    policy_dir_from_environment,
)


def _render(report: StackReport) -> str:
    if not report.managed:
        return f"Nenhuma pilha gerenciada (estado em {report.state_file})."
    lines = [
        f"Pilha {report.run_id} (produto {report.product}, alvo {report.lab_target or 'externo'})",
        f"Em execução: {'sim' if report.running else 'NÃO'}; trava KILL: "
        f"{'ACIONADA' if report.kill_switch else 'desligada'}",
    ]
    if report.zap_url:
        lines.append(f"ZAP: {report.zap_url}; proxy de escopo (login): {report.auth_proxy_url}")
    if report.policy_file:
        lines.append(f"Política: {report.policy_file} (vale até {report.not_after})")
    if report.audit_file:
        lines.append(f"Auditoria do proxy: {report.audit_file}")
    lines.extend(
        f"  {s.project}/{s.service}: {s.state} {s.health}".rstrip() for s in report.services
    )
    lines.extend(f"  alvo {name}: {url}" for name, url in report.target_urls.items())
    lines.extend(f"Aviso: {warning}" for warning in report.warnings)
    return "\n".join(lines)


def _render_stop(report: StopReport) -> str:
    created = "criada agora" if report.kill_created else "já existia"
    zap = (
        f"{report.zap_scans_stopped} varredura(s) do ZAP parada(s)"
        if report.zap_reachable
        else f"ZAP inacessível ({report.zap_message}); só a trava do proxy foi acionada"
    )
    return (
        f"Trava de emergência acionada: {report.kill_file} ({created}). {zap}.\n"
        "O proxy nega todo pedido novo até ser recriado (hdast stack up)."
    )


def up_command(
    ctx: typer.Context,
    product: Annotated[
        str, typer.Argument(help="Nome do produto (slug) cujo perfil define a política.")
    ],
    vulnerable: Annotated[
        bool | None,
        typer.Option(
            "--vulnerable/--secure", help="Modo do alvo de laboratório; sem a flag, o padrão dele."
        ),
    ] = None,
    token_ttl: Annotated[
        int | None,
        typer.Option("--token-ttl", min=5, max=86400, help="Vida do token do alvo, em segundos."),
    ] = None,
    build: Annotated[
        bool, typer.Option("--build", help="Reconstrói as imagens locais antes de subir.")
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout", min=30, max=1800, help="Prazo, em segundos, para ficar saudável."
        ),
    ] = DEFAULT_UP_TIMEOUT_SECONDS,
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Gera a política do proxy a partir do perfil e sobe ZAP, proxy e alvo de laboratório."""
    request = StackUpRequest(
        product=product,
        vulnerable=vulnerable,
        token_ttl_seconds=token_ttl,
        build=build,
        timeout_seconds=timeout,
    )
    report = build_stack_manager(products_dir).up(request)
    state = get_state(ctx)
    emit(
        build_success(report.model_dump(mode="json"), report.run_id),
        json_mode=state.json_mode,
        human=_render(report),
    )


def status_command(ctx: typer.Context) -> None:
    """Mostra a pilha gerenciada: serviços, política, auditoria e se a trava está acionada."""
    report = build_stack_manager(None).status()
    emit(
        build_success(report.model_dump(mode="json"), report.run_id),
        json_mode=get_state(ctx).json_mode,
        human=_render(report),
    )


def down_command(ctx: typer.Context) -> None:
    """Derruba o que `stack up` subiu e esquece o estado (a auditoria é mantida)."""
    report = build_stack_manager(None).down()
    human = (
        "Nada a derrubar: não há pilha gerenciada."
        if not report.managed
        else (f"Pilha {report.run_id} derrubada. Auditoria mantida em {report.audit_file}.")
    )
    emit(
        build_success(report.model_dump(mode="json"), report.run_id),
        json_mode=get_state(ctx).json_mode,
        human=human,
    )


def stop_command(ctx: typer.Context) -> None:
    """Trava de emergência: nega todo pedido novo no proxy e para as varreduras do ZAP."""
    stopper = open_zap_stopper()
    try:
        report = build_stack_manager(None).stop(stopper, policy_dir_from_environment())
    finally:
        stopper.close()
    emit(
        build_success(report.model_dump(mode="json")),
        json_mode=get_state(ctx).json_mode,
        human=_render_stop(report),
    )


def build_stack_app() -> typer.Typer:
    """Cria o grupo `hdast stack` com seus subcomandos."""
    stack_app = typer.Typer(
        help="Pilha de contêineres do laboratório (ZAP, proxy de escopo, alvo)."
    )
    stack_app.command("up")(up_command)
    stack_app.command("status")(status_command)
    stack_app.command("down")(down_command)
    return stack_app
