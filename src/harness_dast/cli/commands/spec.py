"""Comando `hdast spec inspect`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.inspect_report import SpecInspection
from harness_dast.cli.composition import build_inspect_spec
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.domain.api_summary import DEFAULT_BUDGET_CHARS, MAX_BUDGET_CHARS, MIN_BUDGET_CHARS


def _document(present: bool, valid: bool, count: int) -> str:
    if not present:
        return "ausente"
    return f"{count} item(ns), {'válido' if valid else 'COM PROBLEMAS'}"


def _account_lines(result: SpecInspection) -> list[str]:
    by_account: dict[str, list[str]] = {}
    for item in result.operation_accounts:
        by_account.setdefault(item.account, []).append(item.operation_id)
    return [f"  conta {account}: {', '.join(names)}" for account, names in by_account.items()]


def _render(result: SpecInspection) -> str:
    summary = result.summary
    rules, flows = result.data_rules, result.flows
    lines = [
        f"OpenAPI de {result.product}: {summary.title} {summary.version} "
        f"({summary.operation_count} operação(ões); {summary.omitted_operations} fora do resumo)",
        f"Regras de dados: {_document(rules.present, rules.valid, rules.count)}",
        f"Encadeamentos: {_document(flows.present, flows.valid, flows.count)}",
    ]
    if result.servers_out_of_scope:
        lines.append(f"Servidores fora do escopo: {', '.join(result.servers_out_of_scope)}")
    lines.extend(
        f"  nunca enviada: {n.method} {n.path} [{n.reason}] {n.message}" for n in result.not_sent
    )
    lines.extend(f"  regra sem campo: #{r.number} ({r.field})" for r in result.unused_rules)
    lines.extend(f"  precisa de regra: {n.operation_id}: {n.message}" for n in result.needs_rule)
    lines.extend(f"  [{i.code}] {i.message}" for i in result.issues)
    lines.extend(_account_lines(result))
    if result.suspicious_operations:
        lines.append(
            "Operações que parecem destrutivas (considere scope.deny_paths): "
            + ", ".join(result.suspicious_operations)
        )
    return "\n".join(lines)


def inspect_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    budget: Annotated[
        int,
        typer.Option(
            "--budget",
            min=MIN_BUDGET_CHARS,
            max=MAX_BUDGET_CHARS,
            help="Teto, em caracteres, do JSON do resumo da API.",
        ),
    ] = DEFAULT_BUDGET_CHARS,
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Resume o OpenAPI e confere regras e encadeamentos, sem tocar o alvo."""
    state = get_state(ctx)
    result = build_inspect_spec(products_dir).execute(product, budget)
    emit(
        build_success(result.model_dump(mode="json")),
        json_mode=state.json_mode,
        human=_render(result),
    )


def build_spec_app() -> typer.Typer:
    """Cria o grupo `hdast spec` com seus subcomandos."""
    spec_app = typer.Typer(help="Comandos do OpenAPI do produto.")
    spec_app.command("inspect")(inspect_command)
    return spec_app
