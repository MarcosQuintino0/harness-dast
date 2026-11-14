"""Registro de cada invocação no diário de comandos (ADR 0033).

`run_app` chama `record_invocation` uma vez por invocação, depois do desfecho: é o ponto único
por onde todo comando passa; nenhum comando sabe do diário. A descrição do comando (subcomando,
flags e argumentos) vem da própria árvore do Click, reconhecendo só o que a pessoa digitou, e
os valores passam pela redação do projeto em `domain.command_journal`.

Falha ao gravar o diário NUNCA derruba o comando: vira um aviso no log estruturado.

Decisão (ADR 0033): o painel que `run`, `report` e `panel` geram dentro do comando nasce antes de
a linha do próprio comando existir. Por isso, depois de gravar essa linha, o painel do teste é
refeito uma vez: assim o Terminal já mostra o comando que o gerou, sem criar linha "em andamento"
no diário (que tem formato fechado).
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import structlog
import typer
from typer.core import TyperCommand, TyperGroup, TyperOption

from harness_dast.adapters.storage.command_journal import FileCommandJournalStore
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.application.ports import CommandJournalStore
from harness_dast.application.scan_ports import PanelRefresher
from harness_dast.cli.output import CliState, Envelope
from harness_dast.cli.panel_index_composition import build_indexed_panel
from harness_dast.domain.command_journal import JournalEntry, build_journal_entry

_log = structlog.get_logger()
_PANEL_COMMANDS = frozenset({"run", "report", "panel"})
"""Comandos que geram o painel de um teste dentro deles."""
_PANEL_OK_EXIT_CODES = frozenset({0, 1})


class PanelFactory(Protocol):
    """Monta quem refaz o painel (`build_indexed_panel` na CLI real)."""

    def __call__(
        self, products_dir: Path | None, journal: CommandJournalStore | None
    ) -> PanelRefresher:
        """Monta o gerador do painel, lendo o diário dado (ou o da pasta de estado)."""
        ...


@dataclass(frozen=True)
class Invocation:
    """O que a pessoa digitou, já separado.

    Attributes:
        command: Subcomando por extenso (`probe`, `stack up`).
        product: Argumento `product`, quando o comando tem.
        flags: Pares (nome da flag, valor ou `None` para flag sem valor).
        args: Argumentos posicionais além do produto.
    """

    command: str
    product: str | None
    flags: tuple[tuple[str, str | None], ...]
    args: tuple[str, ...]


def default_journal_store() -> CommandJournalStore:
    """Diário na pasta de estado da pessoa usuária (`HDAST_STATE_DIR` e padrões do sistema)."""
    return FileCommandJournalStore(default_state_dir(os.environ))


def _resolve_command(
    app: typer.Typer, argv: Sequence[str]
) -> tuple[list[str], TyperCommand, typer.Context, list[str]] | None:
    root = typer.main.get_command(app)
    ctx = typer.Context(root, info_name="hdast", resilient_parsing=True)
    command = root
    path: list[str] = []
    rest = list(argv)
    while isinstance(command, TyperGroup):
        name = next((token for token in rest if not token.startswith("-")), None)
        child = command.commands.get(name) if name is not None else None
        if name is None or child is None:
            return None
        path.append(name)
        rest = rest[rest.index(name) + 1 :]
        if isinstance(child, TyperGroup):
            ctx = typer.Context(child, parent=ctx, info_name=name, resilient_parsing=True)
        command = child
    if not isinstance(command, TyperCommand):
        return None
    return path, command, ctx, rest


def _flag_pairs(param: TyperOption, value: object) -> list[tuple[str, str | None]]:
    long_names = [name for name in param.opts if name.startswith("--")]
    name = long_names[0] if long_names else param.opts[0]
    if param.is_flag and isinstance(value, bool):
        if value:
            return [(name, None)]
        return [(param.secondary_opts[0], None)] if param.secondary_opts else []
    values = value if isinstance(value, list | tuple) else [value]
    return [(name, str(item)) for item in values if item is not None]


def describe_invocation(app: typer.Typer, argv: Sequence[str]) -> Invocation | None:
    """Separa subcomando, flags, produto e argumentos do que foi digitado.

    Args:
        app: Aplicação Typer (a árvore de comandos).
        argv: Argumentos sem `--json`.

    Returns:
        A descrição, ou `None` quando `argv` não resolve para um comando (ajuda, comando
        desconhecido) ou pede só a ajuda.
    """
    if "--help" in argv:
        return None
    resolved = _resolve_command(app, argv)
    if resolved is None:
        return None
    path, command, parent, rest = resolved
    ctx = command.make_context(path[-1], rest, parent=parent, resilient_parsing=True)
    flags: list[tuple[str, str | None]] = []
    args: list[str] = []
    product: str | None = None
    for param in command.params:
        source = ctx.get_parameter_source(param.name) if param.name is not None else None
        if param.name is None or source is None or source.name != "COMMANDLINE":
            continue
        value = ctx.params.get(param.name)
        if isinstance(param, TyperOption):
            flags.extend(_flag_pairs(param, value))
        elif param.name == "product" and isinstance(value, str):
            product = value
        else:
            items = value if isinstance(value, list | tuple) else [value]
            args.extend(str(item) for item in items if item is not None)
    return Invocation(" ".join(path), product, tuple(flags), tuple(args))


def record_invocation(
    *,
    store: CommandJournalStore | None,
    app: typer.Typer,
    argv: Sequence[str],
    state: CliState,
    envelopes: Sequence[Envelope],
    exit_code: int,
    started_at: datetime,
    finished_at: datetime,
    panels: PanelFactory | None = None,
) -> None:
    """Grava uma linha no diário e refaz o painel do teste; falha vira aviso e nunca propaga.

    Args:
        store: Diário; `None` usa o da pasta de estado.
        app: Aplicação Typer.
        argv: Argumentos sem `--json`.
        state: Estado da invocação (traz o registro de segredos para a redação).
        envelopes: Envelopes emitidos pelo comando; o último dá o resumo e o `run_id`.
        exit_code: Código de saída do processo.
        started_at: Início da invocação.
        finished_at: Fim da invocação.
        panels: Fábrica do gerador do painel; `None` usa o da CLI real.
    """
    try:
        invocation = describe_invocation(app, argv)
        if invocation is None:
            return
        envelope = envelopes[-1] if envelopes else None
        run_id = envelope.run_id if envelope is not None else None
        flags = invocation.flags
        if run_id is None:
            run_id = next((value for name, value in flags if name == "--run"), None)
        entry = build_journal_entry(
            started_at=started_at,
            finished_at=finished_at,
            command=invocation.command,
            product=invocation.product,
            run_id=run_id,
            flags=flags,
            args=invocation.args,
            exit_code=exit_code,
            error_code=envelope.error.code if envelope and envelope.error else None,
            data=envelope.data if envelope is not None else None,
            mask=state.secrets.mask,
        )
        (store if store is not None else default_journal_store()).append(entry.product, entry)
        _refresh_panel(entry, invocation, store, panels or build_indexed_panel)
    except Exception as error:  # noqa: BLE001 - o diário nunca pode derrubar o comando
        _log.warning("diario_nao_gravado", motivo=type(error).__name__)


def _refresh_panel(
    entry: JournalEntry,
    invocation: Invocation,
    store: CommandJournalStore | None,
    panels: PanelFactory,
) -> None:
    """Refaz o painel do teste depois da linha do comando, para ele já incluí-la."""
    if (
        entry.command not in _PANEL_COMMANDS
        or entry.exit_code not in _PANEL_OK_EXIT_CODES
        or entry.product is None
        or entry.run_id is None
    ):
        return
    products_dir = next(
        (Path(value) for name, value in invocation.flags if name == "--products-dir" and value),
        None,
    )
    panels(products_dir, store).refresh(entry.product, entry.run_id)
