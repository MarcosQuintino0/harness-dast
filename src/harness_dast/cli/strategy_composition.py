"""Monta as consultas locais de estratégia."""

from pathlib import Path

from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.strategy import StrategyService
from harness_dast.cli.approval_composition import open_approval_store
from harness_dast.cli.composition import products_dir_or_default


def build_strategy(products_dir: Path | None) -> StrategyService:
    """Monta serviço sem cliente de rede."""
    root = products_dir_or_default(products_dir)
    return StrategyService(
        FileProfileRepository(root),
        FileStrategyRepository(root),
        open_approval_store(),
        SystemClock(),
        FileProductDocuments(root),
    )
