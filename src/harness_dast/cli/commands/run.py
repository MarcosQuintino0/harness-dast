"""Comando `hdast run`: preflight, probe, scan, authz (opcional) e report em um só processo."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.run import RunRequest, RunResult
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.scan_composition import build_run_pipeline, open_scan_network
from harness_dast.domain.run_summary import RunSummary
from harness_dast.domain.scan_config import FailOn


def _render(summary: RunSummary) -> str:
    lines = [
        f"Run de {summary.product}, pasta {summary.run_id}: {summary.status} "
        f"(saída {summary.exit_code}, {summary.duration_seconds:.0f}s)"
    ]
    for stage in summary.stages:
        detail = f" - {stage.message}" if stage.message else ""
        lines.append(
            f"  {stage.name:<9} {stage.status:<11} {stage.duration_seconds:>7.1f}s{detail}"
        )
    if summary.findings_by_severity is not None:
        counts = ", ".join(f"{name}: {n}" for name, n in summary.findings_by_severity.items())
        lines.append(f"Achados (severidade PROPOSTA pelo ZAP): {counts or 'nenhum'}")
    if summary.authz_findings_by_severity is not None:
        own = ", ".join(f"{name}: {n}" for name, n in summary.authz_findings_by_severity.items())
        lines.append(f"Achados de autorização entre contas (técnica própria): {own}")
    if summary.stop_requested:
        lines.append("A trava de emergência (hdast stop) estava acionada.")
    lines.append("Artefatos: " + (", ".join(sorted(summary.artifacts)) or "nenhum"))
    if summary.cleanup_command:
        lines.append(
            "Os dados de teste criados continuam no alvo. Para limpar, uma pessoa deve rodar:"
        )
        lines.append(
            f"  {summary.cleanup_command}   (simulação; só uma pessoa, num terminal, apaga)"
        )
    return "\n".join(lines)


def _emit(result: RunResult, *, json_mode: bool) -> int:
    summary = result.summary
    data = summary.model_dump(mode="json")
    human = _render(summary)
    if result.error is None:
        emit(build_success(data, summary.run_id), json_mode=json_mode, human=human)
    else:
        emit(
            build_failure_with_data(result.error, data, summary.run_id),
            json_mode=json_mode,
            human=human,
        )
    return summary.exit_code


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def run_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    seed: Annotated[
        int | None, typer.Option("--seed", min=0, help="Semente dos geradores do probe.")
    ] = None,
    skip_scan: Annotated[
        bool, typer.Option("--skip-scan", help="Para depois do probe (laço de regras de dados).")
    ] = False,
    authz: Annotated[
        bool,
        typer.Option(
            "--authz",
            help="Inclui o teste de autorização entre contas (depois do scan): repete pedidos "
            "do probe com outras contas. Manda requisições a mais e escreve no alvo.",
        ),
    ] = False,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(
            "--fail-on",
            help="Sai com 1 se houver achado com esta severidade proposta ou acima "
            "(none, low, medium, high); sobrepõe scan.fail_on do perfil.",
        ),
    ] = None,
    compare: Annotated[
        str | None,
        typer.Option("--compare", help="run_id de uma execução anterior para a comparação."),
    ] = None,
    max_minutes: Annotated[
        int | None,
        typer.Option("--max-minutes", help="Reduz o prazo da varredura (nunca acima do perfil)."),
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
    """Encadeia preflight, probe, scan e report; nunca roda a limpeza."""
    state = get_state(ctx)
    net = open_scan_network(product, products_dir, state.secrets)
    try:
        pipeline = build_run_pipeline(product, products_dir, state.secrets, net)
        result = pipeline.execute(
            RunRequest(
                product=product,
                seed=seed,
                skip_scan=skip_scan,
                authz=authz,
                fail_on=fail_on,
                compare=compare,
                max_minutes=max_minutes,
            )
        )
    finally:
        net.close()
    state.result_emitted = True
    return _emit(result, json_mode=state.json_mode)
