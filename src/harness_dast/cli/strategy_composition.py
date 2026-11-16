"""Monta as consultas locais de estratégia."""

from pathlib import Path

from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.application.strategy import StrategyService
from harness_dast.application.strategy_capture import CaptureStrategy
from harness_dast.cli.approval_composition import formal_profiles, open_approval_store
from harness_dast.cli.composition import build_spec_loader, products_dir_or_default
from harness_dast.cli.stack_composition import load_effective_settings
from harness_dast.observability.logging import SecretRegistry


def build_strategy(products_dir: Path | None) -> StrategyService:
    """Monta serviço sem cliente de rede."""
    root = products_dir_or_default(products_dir)
    return StrategyService(
        FileProfileRepository(root),
        FileStrategyRepository(root),
        open_approval_store(),
        SystemClock(),
        FileProductDocuments(root),
        build_spec_loader(root),
    )


def open_capture_zap(secrets: SecretRegistry) -> ZapApiClient:
    """Abre só controle do ZAP; registra a chave para redação, sem tocar o alvo."""
    settings = load_effective_settings()
    key = settings.zap_api_key.get_secret_value() if settings.zap_api_key else None
    if key:
        secrets.register(key)
    return ZapApiClient(settings.zap_base_url, key)


def build_capture(products_dir: Path | None, zap: ZapApiClient) -> CaptureStrategy:
    """Monta captura sem cliente HTTP de alvo."""
    root = products_dir_or_default(products_dir)
    return CaptureStrategy(
        formal_profiles(root),
        FileStrategyRepository(root),
        open_approval_store(),
        SystemClock(),
        FileProductDocuments(root),
        build_spec_loader(root),
        zap,
    )
