"""Comando de reprodução controlada de achados."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.confirmation import ConfirmationRequest
from harness_dast.cli.composition import open_network
from harness_dast.cli.confirm_composition import build_confirmation
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.errors import ExitCode


def confirm_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto.")],
    run: Annotated[str, typer.Option("--run", help="Execução já varrida.")],
    finding: Annotated[str | None, typer.Option("--finding", help="Fingerprint do achado.")] = None,
    maximum: Annotated[int, typer.Option("--max", help="Máximo de achados, de 1 a 30.")] = 30,
    products_dir: Annotated[
        Path | None, typer.Option("--products-dir", help="Pasta de produtos.")
    ] = None,
) -> int:
    """Compara receitas fixas com controles em operações autorizadas e já varridas."""
    state = get_state(ctx)
    with hold_stack("confirm", product):
        network = open_network(product, products_dir, state.secrets)
        try:
            service = build_confirmation(products_dir, state.secrets, network, run)
            result = service.execute(
                ConfirmationRequest(product=product, run_id=run, finding=finding, maximum=maximum)
            )
            recipe_requests, session_requests = service.traffic
        finally:
            network.close()
    emit(
        build_success(
            {
                "verification": result.model_dump(mode="json"),
                "recipe_requests": recipe_requests,
                "session_requests": session_requests,
            },
            result.run_id,
        ),
        json_mode=state.json_mode,
        human=f"Verificações registradas: {len(result.entries)}. "
        f"Pedidos: receita {recipe_requests}, sessão {session_requests}. Veja verification.json.",
    )
    return int(ExitCode.OK)
