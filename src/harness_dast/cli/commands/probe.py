"""Comando `hdast probe`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.probe import ProbeRequest
from harness_dast.cli.composition import build_probe, open_network
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.domain.errors import (
    ExitCode,
    ExternalToolError,
    HarnessError,
    ScopeViolation,
    TargetError,
)
from harness_dast.domain.probe_result import ProbeResult


def stop_error(result: ProbeResult) -> HarnessError | None:
    """Traduz a parada antecipada do `probe` no erro (e código de saída) correspondente.

    Janela fechada e prazo esgotado são escopo (3); falha do proxy do ZAP é ferramenta
    externa (5); alvo sem resposta é alvo (6). `completed` não é erro.
    """
    message = result.stop_message or "O probe parou antes do fim."
    if result.status in {"stopped_window", "stopped_deadline"}:
        return ScopeViolation(message, hint="O resultado parcial está em data e em probe.json.")
    if result.status == "stopped_zap":
        return ExternalToolError(message, hint="Confira o ZAP e rode o probe de novo.")
    if result.status == "stopped_target_unresponsive":
        return TargetError(message, hint="Aguarde o alvo se recuperar antes de repetir o probe.")
    return None


def _percent(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.0%}"


def _render(result: ProbeResult) -> str:
    summary = result.summary
    mode = "SIMULAÇÃO, nada foi enviado" if result.dry_run else "execução"
    stop = f" - {result.stop_message}" if result.stop_message else ""
    lines = [
        f"Probe de {result.product} ({mode}), run {result.run_id}, semente {result.seed}",
        f"Estado: {result.status}{stop}",
        f"Alcançabilidade: {_percent(summary.reachability)} das tentadas "
        f"({summary.successes}/{summary.operations_sent}); "
        f"{_percent(summary.reachability_all)} de todas ({summary.operations_total})",
    ]
    for item in result.operations:
        status = f" {item.status}" if item.status is not None else ""
        lines.append(f"  {item.outcome:<20} {item.method:<6} {item.path}{status}")
    return "\n".join(lines)


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer; o corpo
# tem poucas linhas e nenhuma regra de negócio.
def probe_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    seed: Annotated[
        int | None,
        typer.Option("--seed", min=0, help="Semente dos geradores; sem ela, sorteia uma."),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Executa só esta operação (repetível)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Monta e confere o escopo, mas não envia nada."),
    ] = False,
    include_delete: Annotated[
        bool,
        typer.Option(
            "--include-delete",
            help="Permite DELETE, só sobre recursos criados nesta execução (flows.yml).",
        ),
    ] = False,
    account: Annotated[
        str | None,
        typer.Option("--account", help="Apelido da conta que envia; sem ele, a primeira."),
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
    """Envia uma requisição válida por operação, pelo ZAP, e mede a alcançabilidade."""
    state = get_state(ctx)
    network = open_network(product, products_dir, state.secrets)
    try:
        use_case = build_probe(products_dir, state.secrets, network)
        request = ProbeRequest(
            product=product,
            seed=seed,
            only=tuple(only or ()),
            dry_run=dry_run,
            include_delete=include_delete,
            account=account,
        )
        result = use_case.execute(request)
    finally:
        network.close()
    run_id = None if result.dry_run else result.run_id
    data = result.model_dump(mode="json")
    error = stop_error(result)
    if error is None:
        emit(build_success(data, run_id), json_mode=state.json_mode, human=_render(result))
        return int(ExitCode.OK)
    failure = build_failure_with_data(error, data, run_id)
    emit(failure, json_mode=state.json_mode, human=_render(result))
    return int(error.exit_code)
