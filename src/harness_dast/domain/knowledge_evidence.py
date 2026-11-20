"""Evidências de execução e proveniência do conhecimento sanitizado."""

from harness_dast.domain.knowledge import KnowledgeEffect, KnowledgeProvenance
from harness_dast.domain.probe_result import ProbeResult, RunManifest
from harness_dast.domain.secret_ref import ProfileModel


class KnowledgeRunEvidence(ProfileModel):
    """Artefatos lidos e tipados em memória; só seus resumos saem na captura."""

    manifest: RunManifest
    probe: ProbeResult
    effects: tuple[KnowledgeEffect, ...] = ()
    authz_product: str | None = None
    authz_run_id: str | None = None
    authz_status: str | None = None
    authz_dry_run: bool | None = None
    provenance: KnowledgeProvenance
