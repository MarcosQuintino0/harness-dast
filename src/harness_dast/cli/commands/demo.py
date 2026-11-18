"""Comando humano `hdast demo`."""

import os
import shutil
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from harness_dast.application.lab_targets import VAMPI
from harness_dast.application.stage_errors import doctor_failure
from harness_dast.cli.approval_composition import build_scope_approvals
from harness_dast.cli.approval_prompt import confirm_product_name
from harness_dast.cli.demo_runtime import (
    DEMO_MINUTES,
    DOCKER_GUIDE,
    DemoSession,
    DemoStep,
    check_demo_environment,
    demo_environment,
    open_demo_session,
)
from harness_dast.cli.output import build_failure_with_data, build_success, emit, get_state
from harness_dast.cli.terminal import is_interactive
from harness_dast.domain.errors import ConfigError, ExitCode

_DEMO_SUMMARY = (
    "O alvo é o VAmPI local, intencionalmente vulnerável, com dados sintéticos.",
    "Nada sai da máquina. As imagens já precisam estar no Docker.",
    f"Reserve cerca de {DEMO_MINUTES} minutos, mais a subida e a parada da pilha.",
)


class DemoApprovalPrompt:
    """Apresenta a execução fixa e confirma com a mesma digitação da aprovação de perfil."""

    def confirm(self, product: str, summary: tuple[str, ...], changes: tuple[str, ...]) -> bool:
        """Usa o nome do comando na confirmação do perfil de laboratório."""
        for line in _DEMO_SUMMARY:
            typer.echo(line, err=True)
        return confirm_product_name("demo")


def _announce(message: str) -> None:
    typer.echo(message, err=True)


def _approve(session: DemoSession) -> bool:
    approved = False
    try:
        session.install_profile()
        approvals = build_scope_approvals(
            session.products, DemoApprovalPrompt(), environ=session.environ
        )
        confirmed = approvals.approve(VAMPI.name, interactive=True).approved
        if confirmed:
            # A aprovação relê o perfil: confere que ela vinculou a cópia do lab, e não outra.
            session.ensure_profile_unchanged()
        approved = confirmed
        return approved
    finally:
        if not approved:
            shutil.rmtree(session.directory)


def _show_recovery(session: DemoSession) -> None:
    _announce(f"Estado da pilha: {session.state}")
    _announce("Defina HDAST_STATE_DIR com essa pasta e rode hdast stack down no Docker local.")


def _execute_demo(session: DemoSession, *, keep: bool) -> tuple[DemoStep, Path | None]:
    started = False
    down: DemoStep | None = None
    report_path = None
    try:
        _announce("Subindo a pilha local do VAmPI…")
        step = session.start()
        if step.code == ExitCode.OK:
            started = True
            _announce("Executando a demonstração…")
            step = session.run()
            report_path = session.report_path(step)
    finally:
        if keep and started:
            _announce("Pilha da demonstração mantida.")
            _show_recovery(session)
        else:
            _announce("Derrubando a pilha da demonstração…")
            down = session.stop()
            if down.code != ExitCode.OK:
                _announce("A pilha da demonstração pode continuar ativa.")
                _show_recovery(session)
    if down is not None and down.code != ExitCode.OK and step.envelope.ok:
        return down, report_path
    return step, report_path


def _offer_report(path: Path) -> None:
    _announce(f"Relatório HTML: {path}")
    if not typer.confirm("Abrir o relatório no navegador?", default=False, err=True):
        return
    try:
        opened = webbrowser.open(path.as_uri())
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        _announce("Não consegui abrir o navegador. Abra o arquivo indicado acima.")


def demo_command(
    ctx: typer.Context,
    keep: Annotated[bool, typer.Option("--keep", help="Deixa a pilha da demo de pé.")] = False,
) -> int:
    """Experimenta o harness no VAmPI local com aprovação digitada."""
    state = get_state(ctx)
    if state.json_mode or not is_interactive():
        raise ConfigError(
            "Só uma pessoa, em terminal interativo, pode executar a demo.",
            hint="Rode hdast demo no seu terminal, sem --json e sem redirecionar a entrada.",
        )
    environ = demo_environment(os.environ)
    report = check_demo_environment(environ)
    if not report.ready:
        error = doctor_failure(report)
        error.hint = f"{error.hint or ''} Veja {DOCKER_GUIDE}.".strip()
        details = "\n".join(check.detail for check in report.checks if check.status == "fail")
        emit(
            build_failure_with_data(error, report.model_dump(mode="json")),
            json_mode=False,
            human=details,
        )
        return int(error.exit_code)

    session = open_demo_session(environ)
    if not _approve(session):
        emit(build_success({"approved": False}), json_mode=False, human="Demonstração cancelada.")
        return int(ExitCode.OK)

    step, report_path = _execute_demo(session, keep=keep)
    state.result_emitted = True
    return _emit_outcome(step, report_path)


def _emit_outcome(step: DemoStep, report_path: Path | None) -> int:
    if report_path is not None:
        _offer_report(report_path)
    data: dict[str, JsonValue] = {**(step.envelope.data or {}), "approved": True}
    data["report_html"] = str(report_path) if report_path is not None else None
    envelope = step.envelope.model_copy(update={"data": data})
    human = f"Demonstração encerrada (saída {int(step.code)})."
    emit(envelope, json_mode=False, human=human)
    return int(step.code)
