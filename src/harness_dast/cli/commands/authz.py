"""Comando `hdast authz`: teste de autorização entre contas sobre o que o `probe` alcançou."""

from pathlib import Path
from typing import Annotated, cast

import typer

from harness_dast.application.authz import AuthzRequest
from harness_dast.application.stage_errors import authz_stop_error
from harness_dast.cli.authz_composition import build_authz
from harness_dast.cli.composition import open_network
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.authz_config import CHECK_ORDER, AuthzCheck
from harness_dast.domain.authz_result import AuthzResult
from harness_dast.domain.errors import ConfigError, ExitCode


def _render(result: AuthzResult) -> str:
    mode = "SIMULAÇÃO, nada foi enviado" if result.dry_run else "execução"
    stop = f" - {result.stop_message}" if result.stop_message else ""
    lines = [
        f"Authz de {result.product} ({mode}), run {result.run_id}",
        f"Estado: {result.status}{stop}; requisições enviadas: {result.requests_sent}",
    ]
    for item in result.checks:
        lines.append(
            f"  {item.check:<16} {item.status:<9} candidatos {item.candidates}, "
            f"testados {item.tested}, achados {item.findings}"
        )
    for finding in result.findings:
        lines.append(
            f"  ACHADO {finding.finding_id} [{finding.proposed_severity}] {finding.technique}: "
            f"{finding.title}"
        )
    if result.not_tested:
        lines.append(f"Sem teste: {len(result.not_tested)} item(ns); veja not_tested em authz.json")
    lines.append(result.notice)
    return "\n".join(lines)


def _checks(values: list[str] | None) -> tuple[AuthzCheck, ...]:
    asked = tuple(values or ())
    unknown = [name for name in asked if name not in CHECK_ORDER]
    if unknown:
        raise ConfigError(
            "Verificação desconhecida em --check.",
            hint=f"Use: {', '.join(CHECK_ORDER)}.",
        )
    # Cada nome já foi conferido contra `CHECK_ORDER`, que é a lista de `AuthzCheck`.
    return cast("tuple[AuthzCheck, ...]", asked)


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def authz_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[
        str, typer.Option("--run", help="run_id do probe cujos pedidos serão repetidos.")
    ],
    check: Annotated[
        list[str] | None,
        typer.Option(
            "--check",
            help="Roda só esta verificação (repetível): horizontal, excessive_data, vertical, "
            "mass_assignment. Só reduz: não liga o que o perfil desligou.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Mostra o plano e o que não pode ser testado; não envia."),
    ] = False,
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> int:
    """Repete pedidos do probe com outras contas e confere campos fora do esquema."""
    state = get_state(ctx)
    request = AuthzRequest(product=product, run_id=run, checks=_checks(check), dry_run=dry_run)
    # A simulação só planeja: não toca o ZAP nem o alvo e não precisa da pilha (ADR 0035).
    with hold_stack("authz", product, needed=not dry_run):
        network = open_network(product, products_dir, state.secrets)
        try:
            result = build_authz(products_dir, state.secrets, network).execute(request)
        finally:
            network.close()
    run_id = None if result.dry_run else result.run_id
    data = result.model_dump(mode="json")
    error = authz_stop_error(result)
    if error is None:
        emit(build_success(data, run_id), json_mode=state.json_mode, human=_render(result))
        return int(ExitCode.OK)
    emit(
        build_failure_with_data(error, data, run_id),
        json_mode=state.json_mode,
        human=_render(result),
    )
    return int(error.exit_code)
