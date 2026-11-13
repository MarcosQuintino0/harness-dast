"""Comando `hdast cleanup`: apaga o lixo de UMA execução, com confirmação de uma pessoa.

O único comando que apaga dados de propósito. Só uma pessoa, num terminal interativo, confirma:
ela DIGITA o nome do produto no prompt. Não existe flag, arquivo nem variável de ambiente que
confirme no lugar dela; sem terminal (stdin e stderr) a limpeza de verdade é recusada. O
`--dry-run` não apaga nada, roda sem terminal e não emite token. Ver ADR 0025.
"""

import sys
from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.cleanup import CleanupReport, CleanupRequest
from harness_dast.cli.composition import build_cleanup
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.domain.cleanup_plan import CleanupPlan
from harness_dast.domain.errors import ExitCode

_STATUS_TEXT = {
    "dry_run": "SIMULAÇÃO: tudo foi desfeito (ROLLBACK), nada foi apagado",
    "committed": "CONFIRMADA: as linhas foram apagadas (COMMIT)",
    "declined": "RECUSADA pela pessoa: tudo foi desfeito (ROLLBACK)",
    "failed": "FALHOU: tudo foi desfeito (ROLLBACK)",
}


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _plan_lines(
    product: str, run_id: str, sha256: str, rows: list[tuple[int, str, int]], max_rows: int
) -> list[str]:
    lines = [f"Limpeza de {product} (execução {run_id})", f"Script SHA-256: {sha256}"]
    lines += [f"  comando {index}: {table} -> {count} linha(s)" for index, table, count in rows]
    total = sum(count for _, _, count in rows)
    lines.append(f"Total: {total} linha(s) (teto do perfil: {max_rows})")
    return lines


def _render(report: CleanupReport) -> str:
    rows = [(s.index, s.table, s.rows) for s in report.statements]
    lines = _plan_lines(report.product, report.run_id, report.script_sha256, rows, report.max_rows)
    lines.append(f"Estado: {_STATUS_TEXT[report.status]}")
    return "\n".join(lines)


class TerminalPrompt:
    """Mostra o plano no stderr e exige que a pessoa digite o nome do produto."""

    def confirm(self, plan: CleanupPlan) -> bool:
        """Devolve `True` só se o texto digitado for exatamente o nome do produto."""
        rows = [(r.index, r.table, r.rows) for r in plan.results]
        text = "\n".join(
            _plan_lines(plan.product, plan.run_id, plan.script_sha256, rows, plan.max_rows)
        )
        typer.echo(text, err=True)
        typer.echo("Estas linhas serão APAGADAS DE VERDADE no banco de testes.", err=True)
        answer = typer.prompt(
            f"Digite '{plan.product}' para confirmar (outra coisa cancela)",
            default="",
            show_default=False,
            err=True,
        )
        return str(answer).strip() == plan.product


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def cleanup_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[str, typer.Option("--run", help="Identificador da execução a limpar.")],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Executa os comandos, mostra as contagens e DESFAZ tudo (não exige terminal).",
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
    """Apaga o lixo de uma execução; só uma pessoa, digitando no terminal, confirma."""
    state = get_state(ctx)
    use_case = build_cleanup(products_dir, state.secrets, TerminalPrompt())
    request = CleanupRequest(
        product=product,
        run_id=run,
        dry_run=dry_run,
        confirm_token=None,
        interactive=_is_interactive(),
    )
    report = use_case.execute(request)
    emit(
        build_success(report.model_dump(mode="json"), report.run_id),
        json_mode=state.json_mode,
        human=_render(report),
    )
    return int(ExitCode.OK)
