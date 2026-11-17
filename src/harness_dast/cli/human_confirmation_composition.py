"""Montagem do registro humano, sem rede."""

from harness_dast.adapters.reporting.run_files import FileRunArtifacts
from harness_dast.adapters.storage.human_confirmation_store import FileHumanConfirmationStore
from harness_dast.adapters.system_clock import SystemClock
from harness_dast.application.human_confirmation import AcknowledgeFinding
from harness_dast.application.human_confirmation_ports import HumanConfirmationPrompt
from harness_dast.config.settings import load_settings
from harness_dast.observability.logging import SecretRegistry


def build_human_confirmation(
    prompt: HumanConfirmationPrompt, secrets: SecretRegistry
) -> AcknowledgeFinding:
    """Monta o caso de uso a partir da pasta de execuções configurada."""
    runs_dir = load_settings().runs_dir
    return AcknowledgeFinding(
        FileHumanConfirmationStore(runs_dir),
        FileRunArtifacts(runs_dir),
        prompt,
        SystemClock(),
        secrets.mask,
    )
