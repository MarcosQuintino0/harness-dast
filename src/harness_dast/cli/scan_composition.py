"""Montagem manual de `scan` e `report` (arquivo à parte: `composition.py` é compartilhado).

Sem contêiner de injeção. `open_scan_network` abre o cliente do ZAP com a API de varredura
além do cliente do alvo; `build_scan` e `build_report` ligam as portas aos adaptadores reais.
"""

from pathlib import Path

import structlog

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.reporting.sinks import (
    HtmlReportSink,
    JsonFindingsSink,
    MarkdownReportSink,
)
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemEntropy, SystemSleeper
from harness_dast.adapters.zap.scan_client import ZapScanClient
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.metrics import MetricsRecorder
from harness_dast.application.panel_index_ports import ScanLive
from harness_dast.application.report import Report
from harness_dast.application.run import RunPipeline
from harness_dast.application.scan import Scan
from harness_dast.cli.approval_composition import checked_profiles
from harness_dast.cli.authz_composition import build_authz
from harness_dast.cli.composition import (
    NetworkHandle,
    SharedServices,
    build_preflight,
    build_probe,
    build_spec_loader,
    harness_version,
    open_network,
    products_dir_or_default,
)
from harness_dast.cli.negative_composition import build_negative
from harness_dast.cli.panel_index_composition import build_indexed_panel, build_live_board
from harness_dast.cli.secrets_composition import build_secret_provider
from harness_dast.cli.stack_composition import (
    load_effective_settings,
    open_kill_switch,
    open_proxy_audit,
)
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.run import RunId
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
    settings = load_effective_settings()
    api_key = settings.zap_api_key.get_secret_value() if settings.zap_api_key else None
    return ScanNetwork(network, ZapScanClient(settings.zap_base_url, api_key))


def build_scan(
    products_dir: Path | None,
    secrets: SecretRegistry,
    net: ScanNetwork,
    shared: SharedServices | None = None,
    live: ScanLive | None = None,
) -> Scan:
    """Monta o caso de uso `hdast scan` sobre a rede já aberta."""
    root = products_dir_or_default(products_dir)
    runs_dir = load_settings().runs_dir
    services = shared or SharedServices(kill_switch=open_kill_switch())
    return Scan(
        profiles=checked_profiles(root),
        specs=build_spec_loader(root),
        documents=FileProductDocuments(root),
        secrets=build_secret_provider(),
        vault=secrets,
        client=net.network.client,
        zap=net.network.zap,
        scanner=net.scanner,
        store=FileRunStore(runs_dir),
        artifacts=FileRunArtifacts(runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        token_cache=net.network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
        proxy_audit=open_proxy_audit(),
        live=live,
    )


def build_run_pipeline(
    product: str, products_dir: Path | None, secrets: SecretRegistry, net: ScanNetwork
) -> RunPipeline:
    """Monta o `run`: as etapas sobre a MESMA rede, cache de tokens e orçamento de login.

    Raises:
        ConfigError: Perfil inválido ou configuração `HDAST_*` inválida.
    """
    root = products_dir_or_default(products_dir)
    profiles = checked_profiles(root)
    clock = SystemClock()
    kill_switch = open_kill_switch()
    shared = SharedServices(
        login_budget=LoginBudget(profiles.load(product).login_limit, clock, SystemSleeper()),
        kill_switch=kill_switch,
    )
    runs_dir = load_settings().runs_dir
    board = build_live_board(products_dir, kill_switch)
    return RunPipeline(
        profiles=profiles,
        preflight=build_preflight(products_dir, secrets, net.network, shared),
        probe=build_probe(products_dir, secrets, net.network, shared),
        scan=build_scan(products_dir, secrets, net, shared, live=board),
        report=build_report(products_dir, with_panel=False),
        metrics=build_metrics(products_dir),
        panel=build_indexed_panel(products_dir),
        live=board,
        authz=build_authz(products_dir, secrets, net.network, shared),
        negative=build_negative(products_dir, secrets, net.network, shared),
        sink=FileRunArtifacts(runs_dir),
        kill_switch=kill_switch,
        clock=clock,
        run_id_fallback=RunId.create(
            started_at=clock.now(), product=product, suffix=SystemEntropy().hex_suffix()
        ).value,
    )


def build_report(products_dir: Path | None, *, with_panel: bool = True) -> Report:
    """Monta o caso de uso `hdast report` (sem rede).

    `with_panel=False` é para o `run`, que gera o painel por último, depois de gravar `run.json`.
    """
    runs_dir = load_settings().runs_dir
    try:
        audit = open_proxy_audit()
    except ConfigError as error:
        # Os sinais da cerca (ADR 0049) são secundários: estado de pilha ilegível só os desliga.
        structlog.get_logger().warning("signals_audit_unavailable", reason=error.message)
        audit = None
    return Report(
        profiles=FileProfileRepository(products_dir_or_default(products_dir)),
        artifacts=FileRunArtifacts(runs_dir),
        sinks=(
            JsonFindingsSink(runs_dir),
            MarkdownReportSink(runs_dir),
            HtmlReportSink(runs_dir),
        ),
        clock=SystemClock(),
        harness_version=harness_version(),
        metrics=build_metrics(products_dir),
        panel=build_indexed_panel(products_dir) if with_panel else None,
        proxy_audit=audit,
        specs=build_spec_loader(products_dir_or_default(products_dir)),
    )


def build_metrics(products_dir: Path | None) -> MetricsRecorder:
    """Monta o gravador do `metrics.json` (ADR 0031); sem pilha gerenciada não há lacunas."""
    runs_dir = load_settings().runs_dir
    try:
        audit = open_proxy_audit()
    except ConfigError as error:
        # A medição é secundária: um estado de pilha ilegível só tira as lacunas do arquivo.
        structlog.get_logger().warning("metrics_audit_unavailable", reason=error.message)
        audit = None
    return MetricsRecorder(
        profiles=FileProfileRepository(products_dir_or_default(products_dir)),
        artifacts=FileRunArtifacts(runs_dir),
        proxy_audit=audit,
        clock=SystemClock(),
        harness_version=harness_version(),
    )
