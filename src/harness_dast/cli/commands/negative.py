"""Comando `hdast negative`: valores que o esquema proíbe, sobre o que o `probe` alcançou."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.negative import NegativeRequest
from harness_dast.application.stage_errors import negative_stop_error
from harness_dast.cli.composition import open_network
from harness_dast.cli.negative_composition import build_negative
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.negative_result import NegativeResult


def _render(result: NegativeResult) -> str:
    mode = "SIMULAÇÃO, nada foi enviado" if result.dry_run else "execução"
    stop = f" - {result.stop_message}" if result.stop_message else ""
    lines = [
        f"Negative de {result.product} ({mode}), run {result.run_id}",
        f"Estado: {result.status}{stop}; requisições enviadas: {result.requests_sent}; "
        f"operações testadas: {result.operations_tested}",
    ]
    for item in result.by_class:
        if item.planned or item.sent:
            lines.append(
                f"  {item.case_class:<17} planejados {item.planned}, enviados {item.sent}, "
                f"rejeitados {item.rejected}, aceitos {item.accepted}, "
                f"5xx {item.server_error}, sem conclusão {item.inconclusive}"
            )
    for case in result.plan:
        lines.append(
            f"  PLANO {case.method} {case.path} {case.location}:{case.field} "
            f"{case.case_class} ({case.declared})"
        )
    for finding in result.findings:
        lines.append(
            f"  ACHADO {finding.finding_id} [{finding.proposed_severity}] {finding.technique}: "
            f"{finding.title}"
        )
    if result.created_resources:
        lines.append(
            f"{result.created_resources} POST(s) aceito(s) pode(m) ter criado recurso com valor "
            "inválido: limpe com `hdast cleanup` ou o reset do ambiente."
        )
    if result.not_tested:
        lines.append(
            f"Sem teste: {len(result.not_tested)} item(ns); veja not_tested em negative.json"
        )
    lines.append(result.notice)
    return "\n".join(lines)


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def negative_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[
        str,
        typer.Option(
            "--run",
            help="run_id do probe cujos pedidos serão repetidos com um valor que o esquema proíbe.",
        ),
    ],
    only: Annotated[
        list[str] | None,
        typer.Option(
            "--only",
            help="Testa só esta operação (operationId; repetível). Só reduz.",
        ),
    ] = None,
    max_requests: Annotated[
        int | None,
        typer.Option(
            "--max-requests",
            help="Teto de envios do estágio (casos e restaurações). Só reduz o de "
            "negative.max_requests do perfil; acima dele é erro.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Mostra os casos e o que não pode ser testado; não envia nem grava."
        ),
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
    """Repete pedidos do probe com um valor que o OpenAPI proíbe, um campo por vez."""
    state = get_state(ctx)
    request = NegativeRequest(
        product=product,
        run_id=run,
        only=tuple(only or ()),
        max_requests=max_requests,
        dry_run=dry_run,
    )
    # A simulação só planeja: não toca o ZAP nem o alvo e não precisa da pilha (ADR 0035).
    with hold_stack("negative", product, needed=not dry_run):
        network = open_network(product, products_dir, state.secrets)
        try:
            result = build_negative(products_dir, state.secrets, network).execute(request)
        finally:
            network.close()
    run_id = None if result.dry_run else result.run_id
    data = result.model_dump(mode="json")
    error = negative_stop_error(result)
    if error is None:
        emit(build_success(data, run_id), json_mode=state.json_mode, human=_render(result))
        return int(ExitCode.OK)
    emit(
        build_failure_with_data(error, data, run_id),
        json_mode=state.json_mode,
        human=_render(result),
    )
    return int(error.exit_code)
