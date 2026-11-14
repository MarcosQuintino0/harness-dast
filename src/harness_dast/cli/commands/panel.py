"""Comando `hdast panel`: gera as páginas do painel da execução."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from harness_dast.application.panel import PanelOutcome, PanelRequest
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.panel_composition import build_panel
from harness_dast.domain.panel_format import RUN_STATE_WORDS


def _render(outcome: PanelOutcome) -> str:
    severe = (
        "sem relatório de achados"
        if outcome.severe_findings is None
        else f"{outcome.severe_findings} falha(s) grave(s)"
    )
    lines = [
        f"Painel de {outcome.product}, execução {outcome.run_id}: "
        f"{RUN_STATE_WORDS[outcome.verdict]}, {severe}.",
        f"Páginas: {outcome.run_id}/{outcome.directory}/ ({len(outcome.files)} arquivos); "
        f"comece por {outcome.entry}.",
        "Arquivos lidos: " + (", ".join(outcome.sources) or "nenhum"),
    ]
    if outcome.missing:
        lines.append("Não encontrados (aparecem como 'não medido'): " + ", ".join(outcome.missing))
    lines.append("Abra a página no navegador: é um arquivo local, sem internet e sem script.")
    return "\n".join(lines)


def panel_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[
        str | None,
        typer.Option("--run", help="run_id da execução; sem ele, a mais recente do produto."),
    ] = None,
    products_dir: Annotated[
        Path | None,
        typer.Option(
            "--products-dir",
            help="Pasta de produtos; sobrepõe HDAST_PRODUCTS_DIR.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Gera (ou atualiza) as páginas HTML do painel em runs/<run_id>/panel/, sem rede."""
    state = get_state(ctx)
    outcome = build_panel(products_dir).execute(PanelRequest(product=product, run_id=run))
    data: dict[str, JsonValue] = {
        "run_id": outcome.run_id,
        "product": outcome.product,
        "directory": outcome.directory,
        "entry": outcome.entry,
        "files": list(outcome.files),
        "verdict": outcome.verdict,
        "severe_findings": outcome.severe_findings,
        "sources": list(outcome.sources),
        "missing": list(outcome.missing),
    }
    emit(build_success(data, outcome.run_id), json_mode=state.json_mode, human=_render(outcome))
