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
from harness_dast.cli.stack_composition import build_stack_manager, open_state_store
from harness_dast.domain.errors import ConfigError, ExternalToolError
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


def open_capture_zap(
    product: str, products_dir: Path | None, secrets: SecretRegistry
) -> tuple[ZapApiClient, str]:
    """Usa exclusivamente o controle da pilha gerenciada ativa para o produto."""
    try:
        report = build_stack_manager(products_dir).status()
        state = open_state_store().load()
    except ExternalToolError:
        raise ConfigError("Não foi possível confirmar a pilha gerenciada ativa.") from None
    if (
        state is None
        or not report.managed
        or not report.running
        or report.kill_switch
        or state.product != product
        or report.product != product
        or report.run_id != state.run_id
        or report.zap_url != state.zap_url
    ):
        raise ConfigError("Não há pilha gerenciada ativa para este produto.")
    secrets.register(state.zap_api_key)
    return ZapApiClient(state.zap_url, state.zap_api_key), state.zap_url


def build_capture(
    products_dir: Path | None, zap: ZapApiClient, control_url: str
) -> CaptureStrategy:
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
        control_url,
    )
