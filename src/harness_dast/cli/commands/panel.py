"""Comando `hdast panel`: gera as páginas do painel da execução."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from harness_dast.application.panel import PanelRequest
from harness_dast.application.panel_index import IndexedOutcome
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.panel_index_composition import build_indexed_panel
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.panel_format import RUN_STATE_WORDS


def _render(result: IndexedOutcome) -> str:
    indexes = "Índices refeitos em runs/: " + ", ".join(result.indexes)
    outcome = result.panel
    if outcome is None:
        return (
            f"{indexes}\nAbra runs/index.html no navegador: é um arquivo local, sem internet e "
            "sem script."
        )
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
    lines.append(indexes)
    lines.append("Abra a página no navegador: é um arquivo local, sem internet e sem script.")
    return "\n".join(lines)


def panel_command(
    ctx: typer.Context,
    product: Annotated[
        str | None, typer.Argument(help="Nome do produto (slug); dispensável com --index.")
    ] = None,
    run: Annotated[
        str | None,
        typer.Option("--run", help="run_id da execução; sem ele, a mais recente do produto."),
    ] = None,
    index: Annotated[
        bool,
        typer.Option(
            "--index",
            help="Só refaz os índices (runs/index.html e o histórico de cada produto), sem gerar "
            "painel de teste. Os índices também são refeitos sempre que um painel é gerado.",
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
) -> None:
    """Gera (ou atualiza) o painel de um teste e os índices (runs/index.html), sem rede."""
    state = get_state(ctx)
    panel = build_indexed_panel(products_dir)
    if index:
        if product is not None or run is not None:
            raise ConfigError(
                "--index não se combina com o produto nem com --run.",
                hint="Rode 'hdast panel --index' sozinho, ou 'hdast panel PRODUTO' para um teste.",
            )
        result = panel.rebuild_indexes()
        only: dict[str, JsonValue] = {"indexes": list(result.indexes)}
        emit(build_success(only), json_mode=state.json_mode, human=_render(result))
        return
    if product is None:
        raise ConfigError(
            "Informe o produto, ou use --index para refazer só os índices.",
            hint="Exemplo: hdast panel clinica-piloto   ou   hdast panel --index",
        )
    result = panel.execute(PanelRequest(product=product, run_id=run))
    outcome = result.panel
    if outcome is None:  # garantido por `execute`; protege o tipo
        raise ConfigError("O painel não devolveu o resultado do teste.")
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
        "indexes": list(result.indexes),
    }
    emit(build_success(data, outcome.run_id), json_mode=state.json_mode, human=_render(result))
