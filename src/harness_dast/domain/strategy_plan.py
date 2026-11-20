"""Snapshot de varredura e comparação conservadora com o plano atual em memória."""

from dataclasses import dataclass, field
from datetime import datetime

from harness_dast.domain.envelope import require_approved_envelope
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_plan import ScanPlan
from harness_dast.domain.scan_policy import ScanLimits, ScanPolicy
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import StrategyBasis


@dataclass(frozen=True)
class CompiledScanPlan:
    """Plano concreto em memória; URLs e corpos não devem ser persistidos ou exibidos."""

    scan_plan: ScanPlan = field(repr=False)
    policy: ScanPolicy
    limits: ScanLimits
    approval_digest: str


def compile_scan_snapshot(
    profile: ProductProfile,
    approval: ScopeApproval | None,
    strategy: Strategy | None,
    now: datetime,
    *,
    baseline: ScanPlan,
    proposed: ScanPlan,
    baseline_policy: ScanPolicy,
    proposed_policy: ScanPolicy,
    baseline_limits: ScanLimits,
    proposed_limits: ScanLimits,
    basis: StrategyBasis | None = None,
) -> CompiledScanPlan:
    """Compara o plano concreto e a política com a referência gerada pelo fluxo atual.

    A comparação preserva ordem e multiplicidade, inclusive pulos e mensagens aprendidas.
    A referência deve ser gerada pelo fluxo existente com seus overrides já validados.
    Não prova regras individuais instaladas no ZAP, nem revalida aprovações futuras.
    """
    envelope = require_approved_envelope(profile, approval)
    if strategy is not None:
        strategy.ensure_compilable(now, basis)
    if (
        baseline != proposed
        or baseline_policy != proposed_policy
        or baseline_limits != proposed_limits
    ):
        raise ConfigError(
            "O plano difere da cobertura ou dos limites de referência.",
            hint="Preserve o plano e a política do perfil aprovado.",
        )
    return CompiledScanPlan(proposed, proposed_policy, proposed_limits, envelope.approval_digest)
