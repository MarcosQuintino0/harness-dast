"""Montagem da pilha gerenciada e da camada de estado sobre a configuração.

O estado gravado por `hdast stack up` (chave do ZAP, endereços, senhas descartáveis do alvo)
só preenche o que a pessoa NÃO definiu: variável de ambiente `HDAST_*` sempre vence, e o valor
do estado nunca sobrescreve um campo vindo do ambiente. Sem pilha gerenciada, nada muda.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import SecretStr

from harness_dast.adapters.docker.compose import DockerComposeCli, default_repo_root
from harness_dast.adapters.docker.crapi_accounts import CrapiAccountProvisioner
from harness_dast.adapters.openapi.spec_loader import FileSpecLoader
from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.scope_proxy.audit_reader import FileProxyAudit
from harness_dast.adapters.scope_proxy.generate import FileProxyPolicyStore
from harness_dast.adapters.scope_proxy.kill_switch import FileKillSwitch
from harness_dast.adapters.storage.product_paths import resolve_product_file
from harness_dast.adapters.storage.stack_state import FileStackStateStore, default_state_dir
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_random import SystemRandom
from harness_dast.adapters.system_runtime import SystemEntropy
from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.application.stack import POLICY_DIR_ENV, StackManager
from harness_dast.application.stack_models import StackState
from harness_dast.cli.approval_composition import (
    formal_profiles,
    open_approval_store,
    open_stack_freshness,
)
from harness_dast.cli.stack_lock_composition import open_stack_lock
from harness_dast.config.settings import Settings, load_settings
from harness_dast.domain.errors import ConfigError

STOP_ZAP_TIMEOUT_SECONDS = 5.0


def open_state_store(environ: Mapping[str, str] | None = None) -> FileStackStateStore:
    """Armazém do estado da pilha na pasta de estado da pessoa usuária."""
    return FileStackStateStore(default_state_dir(os.environ if environ is None else environ))


def _overlay(settings: Settings, state: StackState) -> Settings:
    given = settings.model_fields_set
    update: dict[str, object] = {}
    if "zap_base_url" not in given:
        update["zap_base_url"] = state.zap_url
    if "zap_api_key" not in given:
        update["zap_api_key"] = SecretStr(state.zap_api_key)
    if "auth_proxy_url" not in given:
        update["auth_proxy_url"] = state.auth_proxy_url
    return settings.model_copy(update=update)


def load_effective_settings() -> Settings:
    """Configuração do ambiente completada pelo estado da pilha gerenciada, se houver.

    Raises:
        ConfigError: Variável `HDAST_*` inválida ou arquivo de estado inválido.
    """
    settings = load_settings()
    state = open_state_store().load()
    return settings if state is None else _overlay(settings, state)


def layered_environ() -> Mapping[str, str]:
    """Ambiente para resolver `secret_ref: env:`: o do processo, completado pelo estado.

    As senhas descartáveis do alvo de laboratório só entram aqui se a variável não estiver
    definida no ambiente; e só são lidas quando um `secret_ref` do perfil cita o nome.

    Raises:
        ConfigError: Arquivo de estado inválido.
    """
    state = open_state_store().load()
    extra = state.target_env if state is not None else {}
    return {**extra, **os.environ}


def build_stack_manager(products_dir: Path | None) -> StackManager:
    """Monta o caso de uso da pilha.

    Raises:
        ConfigError: Configuração inválida ou repositório sem `compose.yaml`.
    """
    settings = load_settings()
    root = products_dir if products_dir is not None else settings.products_dir
    profiles = formal_profiles(root)
    approval_dir = open_approval_store().location("demo").parent
    return StackManager(
        profiles=profiles,
        clock=SystemClock(),
        entropy=SystemEntropy(),
        random=SystemRandom(),
        policies=FileProxyPolicyStore(root, approval_dir, profiles.load),
        compose=DockerComposeCli(os.environ),
        states=open_state_store(),
        environ=os.environ,
        repo_root=default_repo_root(),
        running_scans=FileRunArtifacts(settings.runs_dir),
        locks=open_stack_lock(),
        proxy_env=lambda product: _proxy_mount_env(root, approval_dir, product),
        freshness=open_stack_freshness(root),
        crapi_accounts=CrapiAccountProvisioner(),
        specs=FileSpecLoader(
            lambda product, relative: resolve_product_file(root, product, relative)
        ),
    )


def _proxy_mount_env(products_dir: Path, approvals_dir: Path, product: str) -> dict[str, str]:
    """Monta fontes inteiras em leitura e mantem a identidade nao privilegiada no POSIX."""
    try:
        approval = approvals_dir / f"{product}.json"
        owner = approval.stat()
        if os.name == "nt":
            uid, gid = 10001, 10001
        else:
            uid, gid = owner.st_uid, owner.st_gid
            if uid == 0:
                raise ConfigError(
                    "A aprovacao pertence ao root; o proxy nao pode usar essa identidade.",
                    hint="Use uma conta sem privilegios para a pilha.",
                )
        return {
            "HDAST_APPROVAL_DIR": approvals_dir.resolve(strict=True).as_posix(),
            "HDAST_PRODUCT_DIR": (products_dir / product).resolve(strict=True).as_posix(),
            "HDAST_PROXY_UID": str(uid),
            "HDAST_PROXY_GID": str(gid),
            "HDAST_MANAGED_POLICY": "1",
        }
    except OSError:
        raise ConfigError(
            "Nao foi possivel montar as fontes da aprovacao do proxy.",
            hint="Confira as pastas e tente novamente.",
        ) from None


def open_zap_stopper() -> ZapApiClient:
    """Cliente do ZAP com prazo curto para a trava de emergência (usa a configuração efetiva)."""
    settings = load_effective_settings()
    key = settings.zap_api_key.get_secret_value() if settings.zap_api_key else None
    return ZapApiClient(settings.zap_base_url, key, timeout_seconds=STOP_ZAP_TIMEOUT_SECONDS)


def open_kill_switch() -> FileKillSwitch:
    """Leitura da trava de emergência da pilha gerenciada (ou de `HDAST_SCOPE_POLICY_DIR`).

    Raises:
        ConfigError: Arquivo de estado inválido.
    """
    state = open_state_store().load()
    return FileKillSwitch(state.policy_dir if state is not None else policy_dir_from_environment())


def open_proxy_audit() -> FileProxyAudit | None:
    """Leitura da auditoria do proxy da pilha gerenciada; `None` sem pilha.

    Raises:
        ConfigError: Arquivo de estado inválido.
    """
    state = open_state_store().load()
    return None if state is None else FileProxyAudit(state.audit_dir / "audit.jsonl")


def policy_dir_from_environment() -> Path | None:
    """Pasta da política vinda de `HDAST_SCOPE_POLICY_DIR`, para `stop` sem pilha gerenciada."""
    value = os.environ.get(POLICY_DIR_ENV)
    return Path(value) if value else None
