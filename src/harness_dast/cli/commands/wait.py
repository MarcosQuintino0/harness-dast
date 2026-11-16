"""Comando de espera local por uma execução."""

import time
from typing import Annotated

import typer

from harness_dast.adapters.reporting.wait_files import FileWaitReader, ProductWaitReader
from harness_dast.application.ports import WaitReader
from harness_dast.application.wait import WaitRun
from harness_dast.cli.output import build_success, emit, get_state
from harness_dast.cli.stack_lock_composition import open_stack_lock
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError


def wait_command(
    ctx: typer.Context,
    run: Annotated[str | None, typer.Option("--run", help="Identificador da execução.")] = None,
    product: Annotated[
        str | None, typer.Option("--product", help="Produto do run em andamento.")
    ] = None,
    lock: Annotated[
        str | None, typer.Option("--lock", help="Identificador devolvido por espera anterior.")
    ] = None,
    timeout: Annotated[
        int, typer.Option("--timeout", min=1, max=28800, help="Prazo de espera em segundos.")
    ] = 600,
) -> None:
    """Aguarda o resultado do run sem tocar o alvo."""
    if (run is None) == (product is None) or (run is not None and lock is not None):
        raise ConfigError("Informe --run ou --product; --lock exige --product.")
    runs_dir = load_settings().runs_dir
    inspect = open_stack_lock().inspect
    reader: WaitReader = (
        FileWaitReader(runs_dir, inspect)
        if run is not None
        else ProductWaitReader(runs_dir, inspect, lock)
    )
    result = WaitRun(reader, time.monotonic, time.sleep).execute(run or product or "", timeout)
    human = (
        f"Estado: {result.state}; fase: {result.phase}; percentual: {result.progress}; "
        f"resultado: {result.status}; saída do run: {result.exit_code}"
    )
    emit(
        build_success(result.model_dump(mode="json"), result.run_id or run),
        json_mode=get_state(ctx).json_mode,
        human=human,
    )
