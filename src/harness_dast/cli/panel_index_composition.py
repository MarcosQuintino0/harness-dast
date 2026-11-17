"""Montagem manual dos índices e da página ao vivo do painel (ADR 0034): sem contêiner.

Fica à parte de `panel_composition.py` (que monta o painel de UM teste) para que `report`, `run`
e `hdast panel` montem os mesmos objetos. O fuso das datas é o do computador que gera a página.
"""

from datetime import datetime, tzinfo
from pathlib import Path

from harness_dast.adapters.reporting.panel_files import FilePanelFiles
from harness_dast.adapters.reporting.panel_index_files import FilePanelIndexFiles
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.common_ports import CommandJournalStore, KillSwitch
from harness_dast.application.panel_index import IndexedPanel, PanelIndexer
from harness_dast.application.panel_live import LiveBoard
from harness_dast.cli.composition import build_spec_loader, products_dir_or_default
from harness_dast.cli.panel_composition import build_panel
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError


def _local_zone() -> tzinfo:
    zone = datetime.now().astimezone().tzinfo
    if zone is None:
        raise ConfigError(
            "O sistema não informou o fuso horário do computador.",
            hint="Confira a configuração de data e hora do sistema.",
        )
    return zone


def build_indexer(products_dir: Path | None) -> PanelIndexer:
    """Monta o gerador dos índices (sem rede).

    Raises:
        ConfigError: Configuração `HDAST_*` inválida, ou o sistema não informou o fuso local.
    """
    runs_dir = load_settings().runs_dir
    return PanelIndexer(
        files=FilePanelFiles(runs_dir),
        index_files=FilePanelIndexFiles(runs_dir),
        profiles=FileProfileRepository(products_dir_or_default(products_dir)),
        clock=SystemClock(),
        timezone=_local_zone(),
    )


def build_indexed_panel(
    products_dir: Path | None, journal: CommandJournalStore | None = None
) -> IndexedPanel:
    """Monta o painel de um teste que refaz os índices a cada página gerada.

    Args:
        products_dir: Pasta de produtos, ou `None` para a padrão.
        journal: Diário de comandos a ler; `None` usa o da pasta de estado.
    """
    return IndexedPanel(build_panel(products_dir, journal), build_indexer(products_dir))


def build_live_board(products_dir: Path | None, kill_switch: KillSwitch) -> LiveBoard:
    """Monta a página ao vivo do `run` (regrava `panel/live.html` a cada etapa e função)."""
    root = products_dir_or_default(products_dir)
    return LiveBoard(
        files=FilePanelFiles(load_settings().runs_dir),
        profiles=FileProfileRepository(root),
        specs=build_spec_loader(root),
        clock=SystemClock(),
        timezone=_local_zone(),
        kill_switch=kill_switch,
        indexer=build_indexer(products_dir),
    )
