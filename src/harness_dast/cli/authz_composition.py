"""Montagem manual do `authz` (arquivo à parte: `composition.py` é compartilhado).

Sem contêiner de injeção: liga as portas do caso de uso aos adaptadores reais, sobre a mesma
rede (cliente do alvo, cache de tokens) que `probe` e `scan` usam.
"""

import os
from pathlib import Path

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.authz_draft_writer import FileAuthzDraftWriter
from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.adapters.storage.knowledge_repository import FileKnowledgeStore
from harness_dast.adapters.storage.product_documents import FileProductDocuments
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.storage.strategy_repository import FileStrategyRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemEntropy, SystemSleeper
from harness_dast.application.authz import Authz
from harness_dast.application.authz_draft import AuthzDraft
from harness_dast.application.knowledge import load_validated_effects
from harness_dast.cli.approval_composition import checked_profiles
from harness_dast.cli.composition import (
    NetworkHandle,
    SharedServices,
    build_spec_loader,
    products_dir_or_default,
)
from harness_dast.cli.secrets_composition import build_secret_provider
from harness_dast.cli.stack_composition import open_kill_switch
from harness_dast.config.settings import load_settings
from harness_dast.observability.logging import SecretRegistry


def build_authz(
    products_dir: Path | None,
    secrets: SecretRegistry,
    network: NetworkHandle,
    shared: SharedServices | None = None,
    *,
    dry_run: bool = False,
) -> Authz:
    """Monta o caso de uso `hdast authz` sobre a rede já aberta."""
    root = products_dir_or_default(products_dir)
    runs_dir = load_settings().runs_dir
    services = shared or SharedServices(kill_switch=open_kill_switch())
    return Authz(
        profiles=checked_profiles(root, None if dry_run else network.zap, fresh_stack=not dry_run),
        specs=build_spec_loader(root),
        secrets=build_secret_provider(),
        vault=secrets,
        client=network.client,
        store=FileRunStore(runs_dir),
        artifacts=FileRunArtifacts(runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        documents=FileProductDocuments(root),
        value_sources=GeneratorCatalogue,
        entropy=SystemEntropy(),
        token_cache=network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
        mutation_journal=FileMutationJournal(default_state_dir(os.environ) / "mutations"),
        effect_loader=lambda product, profile: load_validated_effects(
            product,
            profile,
            FileKnowledgeStore(root),
            FileStrategyRepository(root),
            SystemClock(),
            network.zap,
        ),
    )


def build_authz_draft(products_dir: Path | None) -> AuthzDraft:
    """Monta o caso de uso `hdast authz --draft-matrix`: só lê perfil e OpenAPI, sem rede.

    Usa o repositório de perfis SEM a conferência de aprovação (como o `spec inspect`): o
    comando não toca o alvo e grava só um arquivo à parte, fora do perfil.
    """
    root = products_dir_or_default(products_dir)
    return AuthzDraft(
        profiles=FileProfileRepository(root),
        specs=build_spec_loader(root),
        artifacts=FileRunArtifacts(load_settings().runs_dir),
        writer=FileAuthzDraftWriter(root),
    )
