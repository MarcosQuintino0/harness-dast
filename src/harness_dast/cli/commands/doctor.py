"""Comando `hdast doctor`: "está tudo pronto para começar?", sem tocar o alvo."""

from pathlib import Path
from typing import Annotated

import typer

from harness_dast.application.doctor_report import DoctorReport
from harness_dast.application.stage_errors import doctor_failure
from harness_dast.cli.composition import build_doctor
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.domain.errors import ExitCode

_MARKS = {"ok": "ok   ", "warn": "AVISO", "fail": "FALHA"}


def _render(report: DoctorReport) -> str:
    scope = f"produto {report.product}" if report.product else "ambiente"
    lines = [f"Doctor ({scope}):"]
    for check in report.checks:
        lines.append(f"  [{_MARKS[check.status]}] {check.id}: {check.detail}")
        if check.operator_detail:
            lines.append(f"          {check.operator_detail}")
    summary = report.summary
    counts = f"{summary.ok} ok, {summary.warn} aviso(s), {summary.fail} falha(s)"
    verdict = "Tudo pronto para começar." if report.ready else "NÃO está pronto para começar."
    lines.append(f"{counts}. {verdict}")
    return "\n".join(lines)


def doctor_command(
    ctx: typer.Context,
    product: Annotated[
        str | None,
        typer.Argument(
            help="Produto a conferir também (perfil, autorização, janela e segredos).",
            show_default=False,
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
    """Confere Docker, imagens, portas, pasta de produtos e, com um produto, o perfil.

    Não envia nada ao alvo, não sobe contêiner e nunca mostra o valor de um segredo.
    """
    state = get_state(ctx)
    report = build_doctor(products_dir, state.secrets).execute(product)
    data = report.model_dump(mode="json")
    if report.ready:
        emit(build_success(data), json_mode=state.json_mode, human=_render(report))
        return int(ExitCode.OK)
    error = doctor_failure(report)
    emit(build_failure_with_data(error, data), json_mode=state.json_mode, human=_render(report))
    return int(error.exit_code)
