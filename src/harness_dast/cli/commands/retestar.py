"""Comando `hdast retestar`: repete só as operações dos achados escolhidos e os classifica."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.adapters.reporting.wait_marker import FileWaitMarker
from harness_dast.application.retest import RetestOutcome, RetestRequest
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.retest_composition import build_retest
from harness_dast.cli.scan_composition import open_scan_network
from harness_dast.cli.stack_lock_composition import hold_stack
from harness_dast.config.settings import load_settings
from harness_dast.domain.api_schema import JsonValue
from harness_dast.domain.retest import DEFAULT_MAX_FINDINGS, MAX_FINDINGS_LIMIT, RetestReport
from harness_dast.domain.scan_config import FailOn

_LABELS = {
    "reproduced": "reproduzido",
    "not_reproduced": "não reproduzido nesta execução",
    "not_tested": "não testado nesta execução",
}


def _render(outcome: RetestOutcome) -> str:
    summary = outcome.run.summary
    lines = [f"Reteste de {summary.product}, pasta {summary.run_id} (saída {outcome.exit_code})"]
    report = outcome.report
    if report is None:
        lines.append("O reteste parou antes de gerar o relatório; não há resultado por achado.")
        if outcome.error is not None:
            lines.append(outcome.error.message)
        return "\n".join(lines)
    lines.append(_counts(report))
    for item in report.entries:
        if item.result == "reproduced":
            lines.append(
                f"  reproduzido: {item.finding_id} {item.proposed_severity} "
                f"{item.method} {item.path_template}"
            )
    lines.append(report.notice)
    return "\n".join(lines)


def _counts(report: RetestReport) -> str:
    counts = report.counts
    from_nuclei = sum(1 for item in report.entries if item.origin == "nuclei")
    nuclei = f", {from_nuclei} deles do Nuclei" if from_nuclei else ""
    return (
        f"{len(report.entries)} achado(s) retestado(s) em {len(report.only)} operação(ões)"
        f"{nuclei}: "
        f"{counts.reproduced} {_LABELS['reproduced']}, "
        f"{counts.not_reproduced} {_LABELS['not_reproduced']}, "
        f"{counts.not_tested} {_LABELS['not_tested']}."
    )


def _emit(outcome: RetestOutcome, *, json_mode: bool) -> int:
    summary = outcome.run.summary
    data: dict[str, JsonValue] = {
        "retest": None if outcome.report is None else outcome.report.model_dump(mode="json"),
        "run": summary.model_dump(mode="json"),
    }
    human = _render(outcome)
    if outcome.error is None:
        emit(build_success(data, summary.run_id), json_mode=json_mode, human=human)
    else:
        emit(
            build_failure_with_data(outcome.error, data, summary.run_id),
            json_mode=json_mode,
            human=human,
        )
    return outcome.exit_code


# Passa de 40 linhas porque quase todas são a declaração das opções do Typer.
def retestar_command(
    ctx: typer.Context,
    product: Annotated[str, typer.Argument(help="Nome do produto (slug).")],
    run: Annotated[
        str, typer.Option("--run", help="run_id da execução anterior, de onde vêm os achados.")
    ],
    finding: Annotated[
        list[str] | None,
        typer.Option(
            "--finding",
            help="Fingerprint de um achado da execução anterior (repetível). Sem ele, "
            "retesta os achados de severidade alta e média.",
        ),
    ] = None,
    max_findings: Annotated[
        int,
        typer.Option(
            "--max",
            min=1,
            max=MAX_FINDINGS_LIMIT,
            help="Máximo de achados a retestar (1 a 30).",
        ),
    ] = DEFAULT_MAX_FINDINGS,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(
            "--fail-on",
            help="Sai com 1 se um achado REPRODUZIDO tiver esta severidade ou acima; só "
            "endurece scan.fail_on do perfil.",
        ),
    ] = None,
    max_minutes: Annotated[
        int | None,
        typer.Option("--max-minutes", help="Reduz o prazo da execução (nunca acima do perfil)."),
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
    """Repete só as operações dos achados escolhidos; nunca diz que um achado foi corrigido."""
    state = get_state(ctx)
    # Mesma tomada e mesmos controles do `run`: o reteste só reaproveita o pipeline dele.
    with hold_stack("retestar", product) as holder:
        if holder is None:
            raise RuntimeError("Trava da execução ausente.")
        marker = FileWaitMarker(load_settings().runs_dir, holder.lock_id)
        marker.write("starting", None)
        net = open_scan_network(product, products_dir, state.secrets)
        try:
            retest = build_retest(product, products_dir, state.secrets, net, marker.write)
            outcome = retest.execute(
                RetestRequest(
                    product=product,
                    previous_run_id=run,
                    findings=tuple(finding or ()),
                    max_findings=max_findings,
                    fail_on=fail_on,
                    max_minutes=max_minutes,
                )
            )
            marker.write("finished", outcome.run.summary.run_id)
        finally:
            net.close()
    state.result_emitted = True
    return _emit(outcome, json_mode=state.json_mode)
