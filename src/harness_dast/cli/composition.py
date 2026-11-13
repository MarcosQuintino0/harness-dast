"""Montagem manual das dependências: o único lugar que instancia adaptadores concretos.

Sem contêiner de injeção. Cada função devolve um caso de uso pronto, com as portas ligadas
aos adaptadores reais.
"""

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.http.target_client import HttpxTargetClient, TargetClientSettings
from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.secrets.env_provider import EnvSecretProvider
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.product_scaffolder import (
    FileProductScaffolder,
    default_template_dir,
)
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemEntropy, SystemSleeper
from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.application.init_product import InitProduct
from harness_dast.application.inspect_spec import InspectSpec
from harness_dast.application.preflight import Preflight
from harness_dast.application.probe import Probe
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.config.settings import Settings, load_settings
from harness_dast.domain.probe_policy import REQUEST_TIMEOUT_SECONDS
from harness_dast.observability.logging import SecretRegistry


def _products_dir(override: Path | None) -> Path:
    # A flag tem precedência sobre HDAST_PRODUCTS_DIR; ela só escolhe a pasta, não amplia nada.
    return override if override is not None else load_settings().products_dir


def build_init_product(products_dir: Path | None) -> InitProduct:
    """Monta o caso de uso `hdast init`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    scaffolder = FileProductScaffolder(_products_dir(products_dir), default_template_dir())
    return InitProduct(scaffolder)


def build_validate_profile(products_dir: Path | None) -> ValidateProfile:
    """Monta o caso de uso `hdast profile validate`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    repository = FileProfileRepository(_products_dir(products_dir))
    return ValidateProfile(repository, SystemClock())


def _harness_version() -> str:
    try:
        return version("harness-dast")
    except PackageNotFoundError:  # pragma: no cover - pacote sempre instalado em uso normal
        return "desconhecida"


def _spec_loader(products_dir: Path) -> FileSpecLoader:
    return FileSpecLoader(
        lambda product, relative: resolve_product_file(products_dir, product, relative)
    )


def build_inspect_spec(products_dir: Path | None) -> InspectSpec:
    """Monta o caso de uso `hdast spec inspect`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    root = _products_dir(products_dir)
    return InspectSpec(
        profiles=FileProfileRepository(root),
        specs=_spec_loader(root),
        documents=FileProductDocuments(root),
        value_sources=GeneratorCatalogue,
        clock=SystemClock(),
    )


class NetworkHandle:
    """Peças de rede compartilhadas por `preflight` e `probe` (ZAP e cliente do alvo)."""

    def __init__(self, settings: Settings, secrets: SecretRegistry, *, verify_tls: bool) -> None:
        """Cria os clientes; registra a chave do ZAP para mascaramento.

        Args:
            settings: Configuração `HDAST_*`.
            secrets: Registro de segredos da invocação.
            verify_tls: Se o certificado do alvo é verificado (vem do perfil).
        """
        api_key = settings.zap_api_key.get_secret_value() if settings.zap_api_key else None
        if api_key:
            secrets.register(api_key)
        self.zap = ZapApiClient(settings.zap_base_url, api_key)
        self.client = HttpxTargetClient(
            TargetClientSettings(
                zap_proxy_url=settings.effective_zap_proxy_url,
                auth_proxy_url=settings.auth_proxy_url,
                timeout_seconds=REQUEST_TIMEOUT_SECONDS,
                verify_tls=verify_tls,
                zap_ca_file=settings.zap_ca_file,
            )
        )

    def close(self) -> None:
        """Fecha as conexões do cliente do alvo e do ZAP."""
        self.client.close()
        self.zap.close()


def open_network(product: str, products_dir: Path | None, secrets: SecretRegistry) -> NetworkHandle:
    """Cria o cliente do alvo e o do ZAP; `verify_tls` vem do perfil do produto.

    Raises:
        ConfigError: Perfil inválido ou configuração `HDAST_*` inválida.
    """
    root = _products_dir(products_dir)
    profile = FileProfileRepository(root).load(product)
    return NetworkHandle(load_settings(), secrets, verify_tls=profile.environment.verify_tls)


def build_preflight(
    products_dir: Path | None, secrets: SecretRegistry, network: NetworkHandle
) -> Preflight:
    """Monta o caso de uso `hdast preflight` sobre a rede já aberta."""
    root = _products_dir(products_dir)
    return Preflight(
        profiles=FileProfileRepository(root),
        secrets=EnvSecretProvider(os.environ),
        vault=secrets,
        client=network.client,
        zap=network.zap,
        store=FileRunStore(load_settings().runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        entropy=SystemEntropy(),
        harness_version=_harness_version(),
    )


def build_probe(
    products_dir: Path | None, secrets: SecretRegistry, network: NetworkHandle
) -> Probe:
    """Monta o caso de uso `hdast probe` sobre a rede já aberta."""
    root = _products_dir(products_dir)
    return Probe(
        profiles=FileProfileRepository(root),
        specs=_spec_loader(root),
        documents=FileProductDocuments(root),
        secrets=EnvSecretProvider(os.environ),
        vault=secrets,
        client=network.client,
        zap=network.zap,
        store=FileRunStore(load_settings().runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        entropy=SystemEntropy(),
        value_sources=GeneratorCatalogue,
        harness_version=_harness_version(),
    )
