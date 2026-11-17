"""Caso de uso de leitura do diário de comandos para o painel (ADR 0033)."""

from dataclasses import dataclass

import structlog

from harness_dast.application.common_ports import CommandJournalStore
from harness_dast.domain.command_journal import JournalEntry, slice_for_run

_log = structlog.get_logger()


@dataclass(frozen=True)
class RunJournal:
    """Trecho do diário que pertence a um teste.

    Attributes:
        entries: Comandos do teste, em ordem cronológica.
        skipped_lines: Linhas do diário do produto que estavam corrompidas e foram puladas.
        has_diary: Se o diário do produto tem alguma linha (lida ou pulada), de qualquer teste.
    """

    entries: tuple[JournalEntry, ...]
    skipped_lines: int
    has_diary: bool = False


def load_journal_for_run(store: CommandJournalStore, product: str, run_id: str) -> RunJournal:
    """Comandos que pertencem ao teste `run_id` do produto, em ordem cronológica.

    É o trecho do diário que vai da última linha do teste anterior até a última deste teste
    (regra em `slice_for_run`): inclui `init`, `profile validate`, `doctor` e `stack up`, que
    ainda não têm execução. Linha corrompida é pulada e registrada no log (o painel mostra o
    que conseguiu ler). Não escreve nada.

    Args:
        store: Diário do produto.
        product: Slug do produto.
        run_id: Execução que o painel mostra.

    Returns:
        As linhas do teste (vazias se o diário não existe ou não tem comando dessa execução) e
        quantas linhas corrompidas foram puladas.

    Raises:
        ConfigError: O arquivo do diário existe, mas não pôde ser lido.
    """
    loaded = store.load(product)
    if loaded.skipped_lines:
        _log.warning("diario_linhas_puladas", produto=product, puladas=loaded.skipped_lines)
    return RunJournal(
        slice_for_run(loaded.entries, run_id),
        loaded.skipped_lines,
        has_diary=bool(loaded.entries) or loaded.skipped_lines > 0,
    )
