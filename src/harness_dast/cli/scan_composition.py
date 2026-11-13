"""Montagem manual de `scan` e `report` (arquivo à parte: `composition.py` é compartilhado).

Sem contêiner de injeção. `open_scan_network` abre o cliente do ZAP com a API de varredura
além do cliente do alvo; `build_scan` e `build_report` ligam as portas aos adaptadores reais.
"""

import os
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.sinks import JsonFindingsSink, MarkdownReportSink
from harness_dast.adapters.secrets.env_provider import EnvSecretProvider
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemSleeper
from harness_dast.adapters.zap.scan_client import ZapScanClient
from harness_dast.application.report import Report
from harness_dast.application.scan import Scan
from harness_dast.cli.composition import (
    NetworkHandle,
    _harness_version,
    _products_dir,
    _spec_loader,
    open_network,
)
from harness_dast.config.settings import load_settings
from harness_dast.observability.logging import SecretRegistry


class ScanNetwork:
    """Rede do `scan`: cliente do alvo, controle do ZAP e API de varredura do ZAP."""

    def __init__(self, network: NetworkHandle, scanner: ZapScanClient) -> None:
        """Junta a rede do `probe` e o cliente de varredura.

        Args:
            network: Cliente do alvo e controle do ZAP.
            scanner: Cliente da API de varredura.
        """
        self.network = network
        self.scanner = scanner

    def close(self) -> None:
        """Fecha todas as conexões."""
        self.scanner.close()
        self.network.close()


def open_scan_network(
    product: str, products_dir: Path | None, secrets: SecretRegistry
) -> ScanNetwork:
    """Abre a rede do `scan`; registra a chave do ZAP para mascaramento.

    Raises:
        ConfigError: Perfil inválido ou configuração `HDAST_*` inválida.
    """
    network = open_network(product, products_dir, secrets)
    settings = load_settings()
    api_key = settings.zap_api_key.get_secret_value() if settings.zap_api_key else None
    return ScanNetwork(network, ZapScanClient(settings.zap_base_url, api_key))


def build_scan(products_dir: Path | None, secrets: SecretRegistry, net: ScanNetwork) -> Scan:
    """Monta o caso de uso `hdast scan` sobre a rede já aberta."""
    root = _products_dir(products_dir)
    runs_dir = load_settings().runs_dir
    return Scan(
        profiles=FileProfileRepository(root),
        specs=_spec_loader(root),
        documents=FileProductDocuments(root),
        secrets=EnvSecretProvider(os.environ),
        vault=secrets,
        client=net.network.client,
        zap=net.network.zap,
        scanner=net.scanner,
        store=FileRunStore(runs_dir),
        artifacts=FileRunArtifacts(runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
    )


def build_report(products_dir: Path | None) -> Report:
    """Monta o caso de uso `hdast report` (sem rede)."""
    runs_dir = load_settings().runs_dir
    return Report(
        profiles=FileProfileRepository(_products_dir(products_dir)),
        artifacts=FileRunArtifacts(runs_dir),
        sinks=(JsonFindingsSink(runs_dir), MarkdownReportSink(runs_dir)),
        clock=SystemClock(),
        harness_version=_harness_version(),
    )
