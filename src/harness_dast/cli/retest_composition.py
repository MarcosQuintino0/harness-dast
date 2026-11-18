"""Montagem do `hdast retestar`: o pipeline do `run` mais a leitura e a escrita do reteste."""

from collections.abc import Callable
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.retest import RetestUseCase
from harness_dast.cli.approval_composition import checked_profiles
from harness_dast.cli.composition import products_dir_or_default
from harness_dast.cli.scan_composition import ScanNetwork, build_run_pipeline
from harness_dast.config.settings import load_settings
from harness_dast.observability.logging import SecretRegistry


def build_retest(
    product: str,
    products_dir: Path | None,
    secrets: SecretRegistry,
    net: ScanNetwork,
    observer: Callable[[str, str | None], None] | None = None,
) -> RetestUseCase:
    """Monta o `retestar` sobre o MESMO `RunPipeline` do `run` (todos os controles dele).

    Raises:
        ConfigError: Perfil inválido, escopo sem aprovação ou configuração `HDAST_*` inválida.
    """
    root = products_dir_or_default(products_dir)
    return RetestUseCase(
        profiles=checked_profiles(root, net.network.zap),
        artifacts=FileRunArtifacts(load_settings().runs_dir),
        run=build_run_pipeline(product, products_dir, secrets, net, observer),
        clock=SystemClock(),
    )
