"""Montagem manual das dependências: o único lugar que instancia adaptadores concretos.

Sem contêiner de injeção. Cada função devolve um caso de uso pronto, com as portas ligadas
aos adaptadores reais.
"""

import os
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from harness_dast.adapters.cleanup.oracle_executor import OracleCleanupExecutor
from harness_dast.adapters.cleanup.run_files import FileCleanupRuns
from harness_dast.adapters.cleanup.script_reader import FileCleanupScripts
from harness_dast.adapters.cleanup.tokens import SecretsTokenSource
from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.docker.host import SystemHost
from harness_dast.adapters.http.target_client import HttpxTargetClient, TargetClientSettings
from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.letter_reader import FileLetterReader
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.product_scaffolder import (
    FileProductScaffolder,
    default_template_dir,
)
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemEntropy, SystemSleeper
from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.application.account_session import TokenCache
from harness_dast.application.cleanup import Cleanup
from harness_dast.application.doctor import Doctor
from harness_dast.application.init_from_letter import InitFromLetter
from harness_dast.application.init_product import InitProduct
from harness_dast.application.inspect_spec import InspectSpec
from harness_dast.application.knowledge import ExecutableKnowledge
from harness_dast.application.login_budget import LoginBudget
from harness_dast.application.ports import KillSwitch, OperatorPrompt, SecretPrompt
from harness_dast.application.preflight import Preflight
from harness_dast.application.probe import Probe
from harness_dast.application.secret_admin import SecretAdmin
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.cli.approval_composition import (
    checked_profiles,
    formal_profiles,
    open_approval_store,
)
from harness_dast.cli.secrets_composition import build_credential_store, build_secret_provider
from harness_dast.cli.stack_composition import (
    load_effective_settings,
    open_kill_switch,
    open_state_store,
)
from harness_dast.config.settings import Settings, load_settings
from harness_dast.domain.probe_policy import REQUEST_TIMEOUT_SECONDS
from harness_dast.observability.logging import SecretRegistry


def products_dir_or_default(override: Path | None) -> Path:
    """Pasta de produtos: a flag `--products-dir` ou, sem ela, `HDAST_PRODUCTS_DIR`."""
    # A flag tem precedência; ela só escolhe a pasta, não amplia nada.
    return override if override is not None else load_settings().products_dir


def build_init_product(products_dir: Path | None) -> InitProduct:
    """Monta o caso de uso `hdast init`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    root = products_dir_or_default(products_dir)
    scaffolder = FileProductScaffolder(root, default_template_dir())
    return InitProduct(scaffolder)


def build_init_from_letter(products_dir: Path | None) -> InitFromLetter:
    """Monta o caso de uso `hdast init --from-letter`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    root = products_dir_or_default(products_dir)
    return InitFromLetter(
        FileLetterReader(), FileProductScaffolder(root, default_template_dir()), SystemClock()
    )


def build_validate_profile(products_dir: Path | None) -> ValidateProfile:
    """Monta o caso de uso `hdast profile validate`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    repository = FileProfileRepository(products_dir_or_default(products_dir))
    return ValidateProfile(repository, SystemClock(), open_approval_store())


def harness_version() -> str:
    """Versão instalada do pacote (registrada em manifesto e relatório)."""
    try:
        return version("harness-dast")
    except PackageNotFoundError:  # pragma: no cover - pacote sempre instalado em uso normal
        return "desconhecida"


def build_spec_loader(products_dir: Path) -> FileSpecLoader:
    """Leitor de OpenAPI que só abre arquivos dentro da pasta do produto."""
    return FileSpecLoader(
        lambda product, relative: resolve_product_file(products_dir, product, relative)
    )


def build_inspect_spec(products_dir: Path | None) -> InspectSpec:
    """Monta o caso de uso `hdast spec inspect`.

    Args:
        products_dir: Valor de `--products-dir`, ou `None` para usar `HDAST_PRODUCTS_DIR`.
    """
    root = products_dir_or_default(products_dir)
    return InspectSpec(
        profiles=FileProfileRepository(root),
        specs=build_spec_loader(root),
        documents=FileProductDocuments(root),
        value_sources=GeneratorCatalogue,
        clock=SystemClock(),
    )


@dataclass(frozen=True)
class SharedServices:
    """O que as etapas do `run` compartilham no mesmo processo (além do cache de tokens).

    Attributes:
        login_budget: Orçamento de logins por minuto único para todas as etapas.
        kill_switch: Trava de emergência consultada em todo portão de envio.
    """

    login_budget: LoginBudget | None = None
    kill_switch: KillSwitch | None = None


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
        self.settings = settings
        if api_key:
            secrets.register(api_key)
        self.zap = ZapApiClient(settings.zap_base_url, api_key)
        # Um cache por processo: `preflight` e `probe` no mesmo processo reaproveitam o login.
        self.token_cache = TokenCache()
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
    root = products_dir_or_default(products_dir)
    profile = formal_profiles(root).load(product)
    settings = load_effective_settings()
    return NetworkHandle(settings, secrets, verify_tls=profile.environment.verify_tls)


def build_preflight(
    products_dir: Path | None,
    secrets: SecretRegistry,
    network: NetworkHandle,
    shared: SharedServices | None = None,
) -> Preflight:
    """Monta o caso de uso `hdast preflight` sobre a rede já aberta."""
    root = products_dir_or_default(products_dir)
    services = shared or SharedServices(kill_switch=open_kill_switch())
    return Preflight(
        profiles=checked_profiles(root, network.zap),
        secrets=build_secret_provider(),
        vault=secrets,
        client=network.client,
        zap=network.zap,
        store=FileRunStore(load_settings().runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        entropy=SystemEntropy(),
        harness_version=harness_version(),
        token_cache=network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
    )


def build_probe(
    products_dir: Path | None,
    secrets: SecretRegistry,
    network: NetworkHandle,
    shared: SharedServices | None = None,
    *,
    dry_run: bool = False,
) -> Probe:
    """Monta o caso de uso `hdast probe` sobre a rede já aberta."""
    root = products_dir_or_default(products_dir)
    services = shared or SharedServices(kill_switch=open_kill_switch())
    return Probe(
        profiles=checked_profiles(root, None if dry_run else network.zap),
        specs=build_spec_loader(root),
        documents=FileProductDocuments(root),
        secrets=build_secret_provider(),
        vault=secrets,
        client=network.client,
        zap=network.zap,
        store=FileRunStore(load_settings().runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        entropy=SystemEntropy(),
        value_sources=GeneratorCatalogue,
        harness_version=harness_version(),
        mutation_journal=FileMutationJournal(default_state_dir(os.environ) / "mutations"),
        knowledge_recipes=ExecutableKnowledge(
            FileKnowledgeStore(root),
            FileStrategyRepository(root),
            SystemClock(),
            None if dry_run else network.zap,
        ),
        token_cache=network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
    )


def build_cleanup(
    products_dir: Path | None, secrets: SecretRegistry, prompt: OperatorPrompt
) -> Cleanup:
    """Monta o caso de uso `hdast cleanup` (sem rede: só o banco de testes e arquivos)."""
    root = products_dir_or_default(products_dir)
    return Cleanup(
        profiles=checked_profiles(root, with_knowledge=False),
        scripts=FileCleanupScripts(
            lambda product, relative: resolve_product_file(root, product, relative)
        ),
        runs=FileCleanupRuns(load_settings().runs_dir),
        secrets=build_secret_provider(),
        vault=secrets,
        executor=OracleCleanupExecutor(),
        prompt=prompt,
        tokens=SecretsTokenSource(),
        clock=SystemClock(),
    )


def build_secret_admin(
    products_dir: Path | None, secrets: SecretRegistry, prompt: SecretPrompt
) -> SecretAdmin:
    """Monta o caso de uso `hdast secret` (sem rede: só o perfil e o cofre do sistema)."""
    return SecretAdmin(
        profiles=FileProfileRepository(products_dir_or_default(products_dir)),
        store=build_credential_store(),
        prompt=prompt,
        vault=secrets,
    )


def build_doctor(products_dir: Path | None, secrets: SecretRegistry) -> Doctor:
    """Monta o caso de uso `hdast doctor` (sem rede: só a máquina e o perfil).

    Raises:
        ConfigError: Configuração `HDAST_*` ou arquivo de estado da pilha inválidos.
    """
    root = products_dir_or_default(products_dir)
    clock = SystemClock()
    profiles = FileProfileRepository(root)
    return Doctor(
        host=SystemHost(os.environ),
        profiles=profiles,
        validator=ValidateProfile(profiles, clock, open_approval_store()),
        secrets=build_secret_provider(),
        vault=secrets,
        states=open_state_store(),
        clock=clock,
        environ=os.environ,
        python_version=sys.version_info[:3],
        products_dir=root,
    )
