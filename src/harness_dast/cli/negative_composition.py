"""Montagem manual do `negative` (arquivo à parte: `composition.py` é compartilhado).

Sem contêiner de injeção: liga as portas do caso de uso aos adaptadores reais, sobre a mesma
rede (cliente do alvo, cache de tokens) que `probe`, `scan` e `authz` usam.
"""

import os
from pathlib import Path

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.knowledge_journal import FileMutationJournal
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.storage.stack_state import default_state_dir
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemSleeper
from harness_dast.application.negative import Negative
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


def build_negative(
    products_dir: Path | None,
    secrets: SecretRegistry,
    network: NetworkHandle,
    shared: SharedServices | None = None,
    *,
    dry_run: bool = False,
) -> Negative:
    """Monta o caso de uso `hdast negative` sobre a rede já aberta."""
    root = products_dir_or_default(products_dir)
    runs_dir = load_settings().runs_dir
    services = shared or SharedServices(kill_switch=open_kill_switch())
    return Negative(
        profiles=checked_profiles(root, None if dry_run else network.zap),
        specs=build_spec_loader(root),
        secrets=build_secret_provider(),
        vault=secrets,
        client=network.client,
        store=FileRunStore(runs_dir),
        artifacts=FileRunArtifacts(runs_dir),
        clock=SystemClock(),
        sleeper=SystemSleeper(),
        token_cache=network.token_cache,
        login_budget=services.login_budget,
        kill_switch=services.kill_switch,
        mutation_journal=FileMutationJournal(default_state_dir(os.environ) / "mutations"),
    )
