"""Montagem manual do `nuclei` (arquivo à parte: `composition.py` é compartilhado).

Sem contêiner de injeção: liga as portas do caso de uso aos adaptadores reais, sobre a mesma
rede (cliente do alvo, cache de tokens) que `probe`, `scan` e `authz` usam. O motor e a leitura
da segunda cerca dependem da pilha gerenciada: sem ela (ou sem as pastas da segunda cerca no
estado) a montagem falha fechada, com a orientação de subir a pilha.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from harness_dast.adapters.docker.compose import DockerComposeCli
from harness_dast.adapters.nuclei.engine import DockerNucleiEngine
from harness_dast.adapters.nuclei.jsonl_reader import NucleiJsonlReader
from harness_dast.adapters.nuclei.manifest_reader import load_nuclei_manifest
from harness_dast.adapters.nuclei.secrets_file import NucleiSecretsFile
from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.scope_proxy.nuclei_fence import FileNucleiFence
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemSleeper
from harness_dast.application.nuclei import Nuclei
from harness_dast.application.stack import stack_compose_env
from harness_dast.application.stack_images import (
    NUCLEI_SERVICE,
    OWN_SERVICES,
    StackImages,
    use_local_build,
)
from harness_dast.application.stack_models import StackState
from harness_dast.cli.approval_composition import checked_profiles
from harness_dast.cli.composition import NetworkHandle, SharedServices, products_dir_or_default
from harness_dast.cli.secrets_composition import build_secret_provider
from harness_dast.cli.stack_composition import (
    build_stack_images,
    open_kill_switch,
    open_state_store,
)
from harness_dast.config.settings import load_settings
from harness_dast.domain.errors import ConfigError
from harness_dast.observability.logging import SecretRegistry


def _require_state() -> StackState:
    state = open_state_store().load()
    if state is None:
        raise ConfigError(
            "Não há pilha gerenciada ativa para o Nuclei rodar.",
            hint="Suba a pilha do produto com hdast stack up; ela publica a política da "
            "segunda cerca.",
        )
    return state


def _engine_env(
    state: StackState, images: StackImages, environ: Mapping[str, str]
) -> dict[str, str]:
    """Ambiente do compose do Nuclei: o da pilha mais as referências das imagens (nunca segredo)."""
    references = images.references((*OWN_SERVICES, NUCLEI_SERVICE), local=use_local_build(environ))
    return {**stack_compose_env(state), **images.compose_env(references)}


def build_nuclei(
    products_dir: Path | None,
    secrets: SecretRegistry,
    network: NetworkHandle,
    shared: SharedServices | None = None,
) -> Nuclei:
    """Monta o caso de uso `hdast nuclei` sobre a rede já aberta.

    Raises:
        ConfigError: Sem pilha gerenciada ativa, ou configuração da imagem do Nuclei inválida.
    """
    root = products_dir_or_default(products_dir)
    runs_dir = load_settings().runs_dir
    services = shared or SharedServices(kill_switch=open_kill_switch())
    state = _require_state()
    images = build_stack_images()
    return Nuclei(
        profiles=checked_profiles(root, network.zap),
        load_manifest=load_nuclei_manifest,
        images=images,
        fence=FileNucleiFence(state.nuclei_policy_dir),
        engine=DockerNucleiEngine(
            DockerComposeCli(os.environ), state.projects[0], _engine_env(state, images, os.environ)
        ),
        secrets_writer=NucleiSecretsFile(),
        reader=NucleiJsonlReader(),
        artifacts=FileRunArtifacts(runs_dir),
        secrets=build_secret_provider(),
        vault=secrets,
        client=network.client,
        store=FileRunStore(runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        token_cache=network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
    )
