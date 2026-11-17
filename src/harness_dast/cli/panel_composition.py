"""Montagem manual do painel da execução (ADR 0032): sem contêiner de injeção.

Fica à parte de `scan_composition.py` para que `report`, `run` e o comando `hdast panel` montem o
mesmo caso de uso. O fuso das datas é o do computador que gera a página. O diário de comandos
vem da pasta de estado (`HDAST_STATE_DIR`), a mesma em que o `hdast` o grava.
"""

import os
from datetime import datetime
from pathlib import Path

from harness_dast.adapters.reporting.panel_files import FilePanelFiles
from harness_dast.adapters.storage.command_journal import FileCommandJournalStore
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.application.common_ports import CommandJournalStore
from harness_dast.application.panel import Panel
from harness_dast.application.panel_hooks import CatalogPanelHooks
from harness_dast.cli.composition import build_spec_loader, products_dir_or_default
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError


def build_panel(products_dir: Path | None, journal: CommandJournalStore | None = None) -> Panel:
    """Monta o caso de uso `hdast panel` (sem rede).

    Args:
        products_dir: Pasta de produtos, ou `None` para a padrão.
        journal: Diário de comandos a ler; `None` usa o da pasta de estado.

    Raises:
        ConfigError: Configuração `HDAST_*` inválida, ou o sistema não informou o fuso local.
    """
    root = products_dir_or_default(products_dir)
    runs_dir = load_settings().runs_dir
    zone = datetime.now().astimezone().tzinfo
    if zone is None:
        raise ConfigError(
            "O sistema não informou o fuso horário do computador.",
            hint="Confira a configuração de data e hora do sistema.",
        )
    return Panel(
        profiles=FileProfileRepository(root),
        specs=build_spec_loader(root),
        files=FilePanelFiles(runs_dir),
        timezone=zone,
        hooks=CatalogPanelHooks(journal or FileCommandJournalStore(default_state_dir(os.environ))),
    )
