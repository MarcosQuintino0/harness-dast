"""Comando `hdast scan`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.scan import ScanRequest
from harness_dast.application.stage_errors import scan_stop_error
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.scan_composition import build_scan, open_scan_network
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.errors import ConfigError, ExitCode
from harness_dast.domain.scan_result import ScanResult


def _render(result: ScanResult) -> str:
    mode = "SIMULAÇÃO, nada foi enviado" if result.dry_run else "execução"
    stop = f" - {result.stop_message}" if result.stop_message else ""
    risks = ", ".join(f"{name}: {count}" for name, count in result.alerts_by_risk.items()) or "-"
    lines = [
        f"Scan de {result.product} ({mode}), run {result.run_id}",
        f"Estado: {result.status}{stop}",
        f"Varreduras: {len(result.entries)} de {len(result.planned)} planejadas; "
        f"alertas: {result.alerts_total} ({risks}; severidade proposta pelo ZAP)",
    ]
    if not result.dry_run:
        health = (
            f"{result.health.failures} falha(s) em {result.health.checks} conferência(s)"
            if result.health.enabled
            else "desligada (sem GET de saúde no escopo)"
        )
        removed = "sim" if result.rules_removed else "NÃO: remova as regras hdast- à mão"
        lines.append(f"Guarda de saúde: {health}; regras do Replacer removidas: {removed}")
    for entry in result.entries:
        lines.append(
            f"  {entry.outcome:<10} {entry.method:<6} {entry.path} {entry.progress}% "
            f"{entry.duration_seconds:.0f}s, {entry.alert_count} alerta(s)"
        )
    for skip in result.skipped:
        lines.append(f"  pulada     {skip.method:<6} {skip.path} ({skip.reason})")
    return "\n".join(lines)


def _chosen(flags: list[str] | None, *, no_include_outcomes: bool) -> tuple[str, ...] | None:
    """Sem flag vale o perfil (`None`); `--no-include-outcomes` reduz a nenhuma classe extra."""
    if no_include_outcomes:
        return ()
    return tuple(flags) if flags else None


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def scan_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[str, typer.Option("--run", help="run_id do probe que alimenta a varredura.")],
    only: Annotated[
        list[str] | None, typer.Option("--only", help="Varre só esta operação (repetível).")
    ] = None,
    include_outcome: Annotated[
        list[str] | None,
        typer.Option(
            "--include-outcome",
            help="Escolhe, dentro de scan.include_outcomes do perfil, as classes do probe que "
            "também são varridas (repetível). Só reduz: classe que o perfil não lista é "
            "recusada; só a carta a autoriza.",
        ),
    ] = None,
    no_include_outcomes: Annotated[
        bool,
        typer.Option(
            "--no-include-outcomes",
            help="Ignora scan.include_outcomes do perfil: varre só operações com sucesso.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Mostra o plano; não toca o ZAP nem o alvo."),
    ] = False,
    max_minutes: Annotated[
        int | None,
        typer.Option("--max-minutes", help="Reduz o prazo total (nunca acima do perfil)."),
    ] = None,
    threads: Annotated[
        int | None,
        typer.Option("--threads", help="Reduz as threads por host (nunca acima do perfil)."),
    ] = None,
    account: Annotated[
        str | None,
        typer.Option("--account", help="Conta do login; sem ela, a do probe."),
    ] = None,
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> int:
    """Varre com o ZAP as requisições que o probe ensinou, com limites fixos."""
    state = get_state(ctx)
    if include_outcome and no_include_outcomes:
        raise ConfigError(
            "--include-outcome e --no-include-outcomes não combinam.",
            hint="Use só uma: a primeira escolhe classes do perfil, a segunda as tira todas.",
        )
    # A simulação não toca o ZAP nem o alvo: não precisa da pilha (ADR 0035).
    with hold_stack("scan", product, needed=not dry_run):
        net = open_scan_network(product, products_dir, state.secrets)
        try:
            result = build_scan(products_dir, state.secrets, net, dry_run=dry_run).execute(
                ScanRequest(
                    product=product,
                    run_id=run,
                    only=tuple(only or ()),
                    include_outcomes=_chosen(
                        include_outcome, no_include_outcomes=no_include_outcomes
                    ),
                    dry_run=dry_run,
                    max_minutes=max_minutes,
                    threads=threads,
                    account=account,
                )
            )
        finally:
            net.close()
    run_id = None if result.dry_run else result.run_id
    data = result.model_dump(mode="json")
    error = scan_stop_error(result)
    if error is None:
        emit(build_success(data, run_id), json_mode=state.json_mode, human=_render(result))
        return int(ExitCode.OK)
    emit(
        build_failure_with_data(error, data, run_id),
        json_mode=state.json_mode,
        human=_render(result),
    )
    return int(error.exit_code)
