"""Resumo imutável do envelope de um perfil, sem conceder aprovação."""

from datetime import date

from pydantic import Field, StrictInt

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import PathMode, Scope
from harness_dast.domain.scope_approval import ScopeApproval, check_approval
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests
from harness_dast.domain.secret_ref import ProfileModel
from harness_dast.domain.window import ExecutionWindow


class AuthorizedEnvelope(ProfileModel):
    """Identidade e limites derivados do perfil; não substitui a verificação da aprovação."""

    product: str
    approval_digest: str
    scope: Scope
    path_mode: PathMode
    authorization_valid_until: date
    windows: tuple[ExecutionWindow, ...]
    requests_per_second: float = Field(gt=0, le=50, strict=True, allow_inf_nan=False)
    max_duration_minutes: StrictInt = Field(ge=1, le=480)
    zap_threads_per_host: StrictInt = Field(ge=1, le=8)


def describe_envelope(profile: ProductProfile) -> AuthorizedEnvelope:
    """Deriva resumo para prévia; não verifica nem concede autorização."""
    blocks = block_digests(profile)
    return AuthorizedEnvelope(
        product=profile.product,
        approval_digest=combine_digests(profile.product, blocks),
        scope=profile.scope.to_scope(),
        path_mode=profile.scope.path_mode,
        authorization_valid_until=profile.scope.authorization.valid_until,
        windows=profile.scope.windows,
        requests_per_second=profile.limits.requests_per_second,
        max_duration_minutes=profile.limits.max_duration_minutes,
        zap_threads_per_host=profile.limits.zap_threads_per_host,
    )


def require_approved_envelope(
    profile: ProductProfile, approval: ScopeApproval | None
) -> AuthorizedEnvelope:
    """Exige aprovação vigente do perfil e deriva resumo; não valida janela ou prazo."""
    check_approval(profile, approval).ensure_approved()
    return describe_envelope(profile)
