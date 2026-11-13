"""Comando `hdast preflight`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.preflight_report import PreflightReport
from harness_dast.cli.composition import build_preflight, open_network
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.domain.errors import ExitCode, HarnessError, PreflightError, ScopeViolation


def _render(report: PreflightReport) -> str:
    lines = [f"Preflight de {report.product}:"]
    for check in report.checks:
        mark = "ok   " if check.ok else "FALHA"
        lines.append(f"  [{mark}] {check.id}: {check.detail}")
        if check.operator_detail:
            lines.append(f"          {check.operator_detail}")
    lines.append("Pronto para o probe." if report.ready else "NÃO está pronto para o probe.")
    return "\n".join(lines)


def failure_for(report: PreflightReport) -> HarnessError:
    """Erro (e código de saída) de um preflight que não passou.

    Falha de autorização ou janela é escopo (3); qualquer outra, preflight (4).
    """
    failed = report.first_failure()
    message = f"Preflight não passou: {failed.id}." if failed else "Preflight não passou."
    hint = failed.detail if failed else None
    if failed is not None and failed.kind == "scope":
        return ScopeViolation(message, hint=hint)
    return PreflightError(message, hint=hint)


def preflight_command(
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
) -> int:
    """Confere autorização, janela, segredos, ZAP, saúde do alvo e login de cada conta."""
    state = get_state(ctx)
    network = open_network(product, products_dir, state.secrets)
    try:
        report = build_preflight(products_dir, state.secrets, network).execute(product)
    finally:
        network.close()
    data = report.model_dump(mode="json")
    if report.ready:
        envelope = build_success(data, report.run_id)
        emit(envelope, json_mode=state.json_mode, human=_render(report))
        return int(ExitCode.OK)
    error = failure_for(report)
    failure = build_failure_with_data(error, data, report.run_id)
    emit(failure, json_mode=state.json_mode, human=_render(report))
    return int(error.exit_code)
