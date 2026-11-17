"""Composição do comando de confirmação sobre os adaptadores existentes."""

from pathlib import Path
from secrets import token_hex

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.run_store import FileRunStore
from harness_dast.adapters.storage.verification_store import VerificationStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.adapters.system_runtime import SystemSleeper
from harness_dast.application.confirmation import Confirmation, ConfirmationDependencies
from harness_dast.cli.approval_composition import checked_profiles
from harness_dast.cli.composition import NetworkHandle, products_dir_or_default
from harness_dast.cli.secrets_composition import build_secret_provider
from harness_dast.cli.stack_composition import open_kill_switch
from harness_dast.config.settings import load_settings
from harness_dast.domain.run_ref import require_run_id
from harness_dast.observability.logging import SecretRegistry


def build_confirmation(
    products_dir: Path | None, secrets: SecretRegistry, network: NetworkHandle, run_id: str
) -> Confirmation:
    """Liga as portas ao perfil aprovado, pilha atual e artefatos da execução."""
    valid_run = require_run_id(run_id)
    runs = load_settings().runs_dir
    path = runs / valid_run / "verification.json"
    return Confirmation(
        ConfirmationDependencies(
            profiles=checked_profiles(
                products_dir_or_default(products_dir), network.zap, fresh_stack=True
            ),
            artifacts=FileRunArtifacts(runs),
            verification=VerificationStore(path, secrets.mask),
            existing=path.exists(),
            store=FileRunStore(runs),
            client=network.client,
            secrets=build_secret_provider(),
            vault=secrets,
            clock=SystemClock(),
            sleeper=SystemSleeper(),
            kill_switch=open_kill_switch(),
            token_cache=network.token_cache,
            marker=lambda: token_hex(8),
        )
    )
