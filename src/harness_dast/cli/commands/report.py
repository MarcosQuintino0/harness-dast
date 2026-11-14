"""Comando `hdast report`."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.report import ReportOutcome, ReportRequest
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.scan_composition import build_report
from harness_dast.domain.errors import ExitCode
from harness_dast.domain.report_model import ReportDigest, build_digest
from harness_dast.domain.scan_config import FailOn


def _render(digest: ReportDigest) -> str:
    counts = ", ".join(f"{name}: {count}" for name, count in digest.summary.by_severity.items())
    lines = [
        f"Relatório de {digest.product}, run {digest.run_id}",
        f"Achados: {digest.summary.total} ({counts}); severidade PROPOSTA pelo ZAP.",
        "Arquivos: " + ", ".join(digest.files),
        "Atenção: este relatório não prova segurança; veja 'O que este relatório não testou'.",
    ]
    for item in digest.findings:
        mark = f" [{item.comparison}]" if item.comparison else ""
        lines.append(
            f"  {item.proposed_severity:<13} {item.finding_id} {item.method} "
            f"{item.path_template} {item.title}{mark}"
        )
    if digest.authz is not None:
        lines.append(
            f"Autorização entre contas (técnica própria, não é o ZAP): "
            f"{len(digest.authz.findings)} achado(s)."
        )
        lines += [
            f"  {item.proposed_severity:<13} {item.finding_id} {item.technique} "
            f"{item.method} {item.path_template}"
            for item in digest.authz.findings
        ]
    if digest.comparison:
        lines.append(
            f"Comparação com {digest.comparison.baseline_run_id}: novos {digest.comparison.new}, "
            f"persistentes {digest.comparison.persistent}, não observados "
            f"{digest.comparison.not_observed} (não observado não é corrigido)."
        )
    if digest.exceeds_threshold:
        lines.append(f"Há achado com severidade proposta igual ou acima de {digest.threshold}.")
    return "\n".join(lines)


def _digest(outcome: ReportOutcome) -> ReportDigest:
    return build_digest(
        outcome.report, outcome.files, outcome.threshold, exceeds=outcome.exceeds_threshold
    )


def _metrics_line(outcome: ReportOutcome) -> str:
    if outcome.metrics_file is None:
        return ""
    return f"\nMedição de tempo da execução: {outcome.metrics_file} (só números, sem dado do alvo)."


def _panel_line(outcome: ReportOutcome) -> str:
    if outcome.panel_file is None:
        return ""
    return (
        f"\nPainel da execução: {outcome.report.run_id}/{outcome.panel_file} "
        "(abra no navegador; sem internet e sem script)."
    )


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def report_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[str, typer.Option("--run", help="run_id do probe e do scan.")],
    compare: Annotated[
        str | None,
        typer.Option("--compare", help="run_id de outra execução para marcar novo/persistente."),
    ] = None,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(
            "--fail-on",
            help="Sai com 1 se houver achado com esta severidade proposta ou acima "
            "(none, low, medium, high); sobrepõe scan.fail_on do perfil.",
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
    """Transforma os alertas do scan em achados e grava findings.json, report.md e report.html."""
    state = get_state(ctx)
    outcome = build_report(products_dir).execute(
        ReportRequest(product=product, run_id=run, compare=compare, fail_on=fail_on)
    )
    digest = _digest(outcome)
    emit(
        build_success(digest.model_dump(mode="json"), digest.run_id),
        json_mode=state.json_mode,
        human=_render(digest) + _metrics_line(outcome) + _panel_line(outcome),
    )
    return int(ExitCode.FINDINGS if outcome.exceeds_threshold else ExitCode.OK)
