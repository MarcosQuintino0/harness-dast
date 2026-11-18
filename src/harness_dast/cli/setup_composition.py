"""Montagem do `hdast setup` (ADR 0114): reaproveita `secret` e `profile approve` sem cópia."""

from pathlib import Path

from harness_dast.adapters.storage.applied_defaults import FileAppliedDefaults
from harness_dast.adapters.storage.profile_repository import FileProfileRepository
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.scope_approval_ports import ApprovalPrompt
from harness_dast.application.secret_ports import SecretPrompt
from harness_dast.application.setup_ports import SetupNotifier
from harness_dast.application.setup_product import SetupProduct
from harness_dast.application.validate_profile import ValidateProfile
from harness_dast.cli.approval_composition import build_scope_approvals, open_approval_store
from harness_dast.cli.composition import build_secret_admin
from harness_dast.observability.logging import SecretRegistry


def build_setup_product(
    root: Path,
    secrets: SecretRegistry,
    *,
    secret_prompt: SecretPrompt,
    approval_prompt: ApprovalPrompt,
    notifier: SetupNotifier,
) -> SetupProduct:
    """Monta o caso de uso `hdast setup` (sem rede: perfil, cofre e aprovação locais)."""
    profiles = FileProfileRepository(root)
    return SetupProduct(
        validator=ValidateProfile(profiles, SystemClock(), open_approval_store()),
        profiles=profiles,
        secrets=build_secret_admin(root, secrets, secret_prompt),
        approvals=build_scope_approvals(root, approval_prompt),
        defaults=FileAppliedDefaults(root),
        notifier=notifier,
    )
