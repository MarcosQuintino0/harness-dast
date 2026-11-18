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

from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.common_ports import Clock, CommandJournalStore
from harness_dast.cli.commands.authz import authz_command
from harness_dast.cli.commands.cleanup import cleanup_command
from harness_dast.cli.commands.confirm import confirm_command
from harness_dast.cli.commands.doctor import doctor_command
from harness_dast.cli.commands.finding import build_finding_app
from harness_dast.cli.commands.init import init_command
from harness_dast.cli.commands.knowledge import build_knowledge_app
from harness_dast.cli.commands.mutation import build_mutation_app
from harness_dast.cli.commands.negative import negative_command
from harness_dast.cli.commands.panel import panel_command
from harness_dast.cli.commands.plan import plan_command
from harness_dast.cli.commands.preflight import preflight_command
from harness_dast.cli.commands.probe import probe_command
from harness_dast.cli.commands.profile import build_profile_app
from harness_dast.cli.commands.report import report_command
from harness_dast.cli.commands.retestar import retestar_command
from harness_dast.cli.commands.run import run_command
from harness_dast.cli.commands.scan import scan_command
from harness_dast.cli.commands.secret import build_secret_app
from harness_dast.cli.commands.setup import setup_command
from harness_dast.cli.commands.spec import build_spec_app
from harness_dast.cli.commands.stack import build_stack_app, stop_command
from harness_dast.cli.commands.strategy import build_strategy_app
from harness_dast.cli.commands.version import version_command
from harness_dast.cli.commands.wait import wait_command
from harness_dast.cli.journal_recording import record_invocation
from harness_dast.cli.output import CliState, build_failure, capture_envelopes, emit, get_state
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError, ExitCode, HarnessError, UserInterrupt
from harness_dast.observability.logging import configure_logging

_log = structlog.get_logger()

START_HERE_PANEL = "Comece por aqui"
REGISTRATION_AND_SCOPE_PANEL = "Cadastro e escopo"
TEST_STAGES_PANEL = "Etapas do teste"
RESULTS_AND_RETEST_PANEL = "Resultados e reteste"
ADVANCED_PANEL = "Avançado"


def _register_commands(app: typer.Typer) -> None:
    # O Typer exibe os painéis na ordem em que encontra seus primeiros comandos.
    app.command("doctor", rich_help_panel=START_HERE_PANEL)(doctor_command)
    app.command("setup", rich_help_panel=START_HERE_PANEL)(setup_command)
    app.command("run", rich_help_panel=START_HERE_PANEL)(run_command)
    app.command("report", rich_help_panel=START_HERE_PANEL)(report_command)
    app.command("stop", rich_help_panel=START_HERE_PANEL)(stop_command)

    app.command("init", rich_help_panel=REGISTRATION_AND_SCOPE_PANEL)(init_command)
    app.add_typer(build_profile_app(), name="profile", rich_help_panel=REGISTRATION_AND_SCOPE_PANEL)
    app.add_typer(build_spec_app(), name="spec", rich_help_panel=REGISTRATION_AND_SCOPE_PANEL)
    app.add_typer(build_secret_app(), name="secret", rich_help_panel=REGISTRATION_AND_SCOPE_PANEL)

    app.command("preflight", rich_help_panel=TEST_STAGES_PANEL)(preflight_command)
    app.command("probe", rich_help_panel=TEST_STAGES_PANEL)(probe_command)
    app.command("scan", rich_help_panel=TEST_STAGES_PANEL)(scan_command)
    app.command("authz", rich_help_panel=TEST_STAGES_PANEL)(authz_command)
    app.command("negative", rich_help_panel=TEST_STAGES_PANEL)(negative_command)
    app.command("confirm", rich_help_panel=TEST_STAGES_PANEL)(confirm_command)
    app.command("wait", rich_help_panel=TEST_STAGES_PANEL)(wait_command)
    app.command("plan", rich_help_panel=TEST_STAGES_PANEL)(plan_command)

    app.command("retestar", rich_help_panel=RESULTS_AND_RETEST_PANEL)(retestar_command)
    app.add_typer(build_finding_app(), name="finding", rich_help_panel=RESULTS_AND_RETEST_PANEL)
    app.command("panel", rich_help_panel=RESULTS_AND_RETEST_PANEL)(panel_command)
    app.command("cleanup", rich_help_panel=RESULTS_AND_RETEST_PANEL)(cleanup_command)

    app.add_typer(build_strategy_app(), name="strategy", rich_help_panel=ADVANCED_PANEL)
    app.add_typer(build_knowledge_app(), name="knowledge", rich_help_panel=ADVANCED_PANEL)
    app.add_typer(build_mutation_app(), name="mutation", rich_help_panel=ADVANCED_PANEL)
    app.add_typer(build_stack_app(), name="stack", rich_help_panel=ADVANCED_PANEL)
    app.command("version", rich_help_panel=ADVANCED_PANEL)(version_command)


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

    _register_commands(app)
    return app


def _fail(error: HarnessError, state: CliState) -> int:
    emit(build_failure(error), json_mode=state.json_mode)
    return int(error.exit_code)


def run_app(
    app: typer.Typer,
    args: Sequence[str] | None = None,
    *,
    clock: Clock | None = None,
    journal: CommandJournalStore | None = None,
) -> int:
    """Executa a aplicação, registra o comando no diário e devolve o código de saída.

    O registro no diário (ADR 0033) acontece aqui, uma vez por invocação, depois do desfecho.
    Falha ao gravar o diário nunca muda o código de saída.

    Args:
        app: Aplicação Typer a executar.
        args: Argumentos; `None` usa `sys.argv`.
        clock: Relógio do diário; `None` usa o do sistema.
        journal: Diário de comandos; `None` usa o da pasta de estado (`HDAST_STATE_DIR`).

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
    now = (clock if clock is not None else SystemClock()).now
    started_at = now()
    with capture_envelopes() as envelopes:
        exit_code = _execute(app, argv, state)
    record_invocation(
        store=journal,
        app=app,
        argv=argv,
        state=state,
        envelopes=envelopes,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=now(),
    )
    return exit_code


def _execute(app: typer.Typer, argv: list[str], state: CliState) -> int:
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
