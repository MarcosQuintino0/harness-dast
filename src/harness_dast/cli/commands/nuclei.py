"""Comando `hdast nuclei`: o segundo motor (Nuclei) atrás da segunda cerca (ADR 0122)."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.nuclei import NucleiRequest
from harness_dast.application.stage_errors import nuclei_stop_error
from harness_dast.cli.composition import open_network
from harness_dast.cli.nuclei_composition import build_nuclei
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.nuclei_result import NucleiResult


def _render(result: NucleiResult) -> str:
    stop = f" - {result.stop_message}" if result.stop_message else ""
    login = f"com login da conta {result.account}" if result.logged_in else "sem login"
    lines = [
        f"Nuclei {result.nuclei_version} (modelos {result.templates_version}) em "
        f"{result.product}, run {result.run_id}",
        f"Estado: {result.status}{stop}; {login}; modelos escolhidos: "
        f"{result.templates_selected}; achados: {len(result.findings)}; "
        f"tecnologias identificadas: {len(result.technologies)}",
    ]
    if result.excluded:
        reasons = ", ".join(f"{reason}: {count}" for reason, count in result.excluded)
        lines.append(f"Modelos excluídos por motivo: {reasons}")
    for finding in result.findings:
        record = finding.record
        lines.append(
            f"  ACHADO {finding.finding_id} [{finding.proposed_severity}] {record.template_id} "
            f"{record.method or '-'} {record.matched_path} ({finding.occurrences}x)"
        )
    if result.malformed_lines:
        lines.append(
            f"{result.malformed_lines} linha(s) da saída do Nuclei não puderam ser lidas e "
            "foram descartadas."
        )
    return "\n".join(lines)


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def nuclei_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[
        str,
        typer.Option(
            "--run",
            help="run_id do probe cuja pasta recebe o nuclei.json (o Nuclei só roda com "
            "extra_checks.nuclei no perfil, que vem da carta).",
        ),
    ],
    account: Annotated[
        str | None,
        typer.Option(
            "--account",
            help="Apelido da conta do login do Nuclei (só vale com extra_checks.nuclei_login); "
            "sem ele usa a primeira do perfil.",
        ),
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
    """Roda só o Nuclei (modelos conhecidos) contra o produto, atrás da segunda cerca."""
    state = get_state(ctx)
    request = NucleiRequest(product=product, run_id=run, account=account)
    with hold_stack("nuclei", product):
        network = open_network(product, products_dir, state.secrets)
        try:
            result = build_nuclei(products_dir, state.secrets, network).execute(request)
        finally:
            network.close()
    data = result.model_dump(mode="json")
    error = nuclei_stop_error(result)
    if error is None:
        emit(build_success(data, result.run_id), json_mode=state.json_mode, human=_render(result))
        return int(ExitCode.OK)
    emit(
        build_failure_with_data(error, data, result.run_id),
        json_mode=state.json_mode,
        human=_render(result),
    )
    return int(error.exit_code)
