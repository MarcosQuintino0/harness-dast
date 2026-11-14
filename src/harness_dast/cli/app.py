"""Aplicação Typer do `hdast` e tratador único de erros.

`run_app` é o único ponto que converte exceções em envelope e código de saída:
`HarnessError` mantém seu código; erro de uso vira `USAGE`; qualquer outra exceção
vira `INTERNAL` (saída 10), sem traceback no stdout (o detalhe vai ao log, em stderr).
"""

import io
import sys
from collections.abc import Sequence
from typing import Annotated

import structlog
import typer
from typer.exceptions import TyperException

from harness_dast.cli.commands.authz import authz_command
from harness_dast.cli.commands.cleanup import cleanup_command
from harness_dast.cli.commands.doctor import doctor_command
from harness_dast.cli.commands.init import init_command
from harness_dast.cli.commands.panel import panel_command
from harness_dast.cli.commands.preflight import preflight_command
from harness_dast.cli.commands.probe import probe_command
from harness_dast.cli.commands.profile import build_profile_app
from harness_dast.cli.commands.report import report_command
from harness_dast.cli.commands.run import run_command
from harness_dast.cli.commands.scan import scan_command
from harness_dast.cli.commands.secret import build_secret_app
from harness_dast.cli.commands.spec import build_spec_app
from harness_dast.cli.commands.stack import build_stack_app, stop_command
from harness_dast.cli.commands.version import version_command
from harness_dast.cli.output import CliState, build_failure, emit, get_state
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError, UserInterrupt
from harness_dast.observability.logging import configure_logging

_log = structlog.get_logger()


def build_app() -> typer.Typer:
    """Cria a aplicação Typer com os comandos disponíveis.

    Returns:
        Uma aplicação nova a cada chamada (permite registrar comandos em testes).
    """
    app = typer.Typer(
        name="hdast",
        help="Harness de testes DAST autorizados: o agente propõe, a CLI executa.",
        no_args_is_help=False,
        add_completion=False,
        pretty_exceptions_enable=False,
    )

    @app.callback()
    def configure(
        ctx: typer.Context,
        json_output: Annotated[
            bool, typer.Option("--json", help="Emite o resultado como envelope JSON.")
        ] = False,
    ) -> None:
        """Opções globais."""
        # `run_app` já remove --json de qualquer posição e liga o modo antes do parse; a
        # opção continua declarada para aparecer na ajuda e para o caso de uso direto.
        state = get_state(ctx)
        state.json_mode = state.json_mode or json_output
        settings = load_settings()
        configure_logging(settings.log_level, state.secrets)

    app.command("version")(version_command)
    app.command("doctor")(doctor_command)
    app.command("init")(init_command)
    app.add_typer(build_profile_app(), name="profile")
    app.add_typer(build_spec_app(), name="spec")
    app.command("preflight")(preflight_command)
    app.command("probe")(probe_command)
    app.command("scan")(scan_command)
    app.command("authz")(authz_command)
    app.command("report")(report_command)
    app.command("panel")(panel_command)
    app.command("run")(run_command)
    app.command("cleanup")(cleanup_command)
    app.add_typer(build_stack_app(), name="stack")
    app.add_typer(build_secret_app(), name="secret")
    app.command("stop")(stop_command)
    return app


def _fail(error: HarnessError, state: CliState) -> int:
    emit(build_failure(error), json_mode=state.json_mode)
    return int(error.exit_code)


def run_app(app: typer.Typer, args: Sequence[str] | None = None) -> int:
    """Executa a aplicação e devolve o código de saída do processo.

    Args:
        app: Aplicação Typer a executar.
        args: Argumentos; `None` usa `sys.argv`.

    Returns:
        Código de saída conforme `ExitCode`.
    """
    raw = list(args) if args is not None else sys.argv[1:]
    # --json vale antes e depois do subcomando (ADR 0010: todo comando o aceita). Ele é
    # removido aqui, e não declarado em cada comando, para valer também para os futuros e
    # para erros de uso, que acontecem antes de qualquer callback rodar.
    argv, json_mode = _extract_json_flag(raw)
    state = CliState(json_mode=json_mode)
    # Antes de qualquer coisa: sem isso o structlog padrão escreveria no stdout.
    configure_logging("INFO", state.secrets)
    try:
        return _dispatch(app, argv, state)
    except HarnessError as error:
        return _fail(error, state)
    except TyperException as error:
        usage = ConfigError(error.format_message(), hint="Use --help para ver o uso correto.")
        return _fail(usage, state)
    except (KeyboardInterrupt, typer.Abort):
        return _fail(UserInterrupt("Execução interrompida pela pessoa usuária."), state)
    except Exception:  # noqa: BLE001 - tratador central: nada pode escapar sem envelope
        _log.exception("erro_interno")
        internal = HarnessError(
            "Erro interno inesperado.",
            hint="Veja o log em stderr e reporte o problema ao mantenedor.",
        )
        return _fail(internal, state)


def _extract_json_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Remove `--json` dos argumentos (até um eventual `--`) e diz se estava presente."""
    separator = argv.index("--") if "--" in argv else len(argv)
    head = [arg for arg in argv[:separator] if arg != "--json"]
    return head + argv[separator:], "--json" in argv[:separator]


def _dispatch(app: typer.Typer, argv: list[str], state: CliState) -> int:
    if not argv:
        # Sem comando: no modo humano mostra a ajuda; no modo JSON a ajuda em texto
        # sujaria o stdout, então a resposta é um erro de uso no envelope.
        if state.json_mode:
            raise ConfigError("Nenhum comando informado.", hint="Use hdast --help.")
        argv = ["--help"]
    result = app(args=argv, standalone_mode=False, obj=state)
    # Fora do modo standalone o click NÃO propaga KeyboardInterrupt: ele o captura e
    # devolve 130 como valor de retorno. Sem este teste a interrupção viraria sucesso (0).
    if result == ExitCode.INTERRUPTED and not state.result_emitted:
        raise UserInterrupt("Execução interrompida pela pessoa usuária.")
    # `hdast run` encerra com 130 de propósito (Ctrl+C ou `hdast stop`) e já emitiu o envelope.
    # Um comando que termina com resultado e erro (preflight não pronto, probe interrompido)
    # devolve o próprio código de saída; os demais devolvem `None`.
    return int(result) if isinstance(result, int) else int(ExitCode.OK)


def main() -> int:
    """Ponto de entrada do console script `hdast`.

    Returns:
        Código de saída do processo.
    """
    # As mensagens têm acentos; sem isto, um stdout redirecionado em página de código
    # antiga (cp1252, ASCII) quebraria a saída com UnicodeEncodeError, e o JSON deve ser UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    return run_app(build_app())
