"""Preservação do plano concreto e da aprovação no snapshot de varredura."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.scan_plan import ScanPlan, ScanTarget
from harness_dast.domain.scan_policy import build_limits, build_policy
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import (
    StrategyBasis,
    digest_strategy_document,
    make_strategy_basis,
)
from harness_dast.domain.strategy_plan import compile_scan_snapshot
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile
from tests.unit.domain.test_strategy import choice, data


def test_snapshot_preserva_plano_e_fingerprint() -> None:
    profile = valid_profile()
    approval = approval_for(profile)
    plan = ScanPlan((), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    result = compile_scan_snapshot(
        profile,
        approval,
        None,
        datetime(2026, 11, 16, tzinfo=UTC),
        baseline=plan,
        proposed=plan,
        baseline_policy=policy,
        proposed_policy=policy,
        baseline_limits=limits,
        proposed_limits=limits,
    )

    assert result.scan_plan == plan
    assert result.approval_digest == approval.digest
    with pytest.raises(FrozenInstanceError):
        result.approval_digest = "alterado"  # type: ignore[misc]  # Testa imutabilidade em runtime.


def test_recusa_perda_de_multiplicidade_sem_expor_pedido() -> None:
    profile = valid_profile()
    target = ScanTarget("op", "GET", "/x", 1, "https://secret", "secret")
    baseline = ScanPlan((target, target), (), ())
    proposed = ScanPlan((target,), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    with pytest.raises(ConfigError) as caught:
        compile_scan_snapshot(
            profile,
            approval_for(profile),
            None,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=baseline,
            proposed=proposed,
            baseline_policy=policy,
            proposed_policy=policy,
            baseline_limits=limits,
            proposed_limits=limits,
        )
    assert "secret" not in str(caught.value)


def test_recusa_politica_alterada_e_aprovacao_ausente() -> None:
    profile = valid_profile()
    plan = ScanPlan((), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)
    changed = policy.model_copy(update={"strength": "HIGH"})

    def compile_with(approval: ScopeApproval | None) -> None:
        compile_scan_snapshot(
            profile,
            approval,
            None,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=plan,
            proposed=plan,
            baseline_policy=policy,
            proposed_policy=changed,
            baseline_limits=limits,
            proposed_limits=limits,
        )

    with pytest.raises(ConfigError):
        compile_with(approval_for(profile))
    with pytest.raises(ScopeNotApproved):
        compile_with(None)


def test_snapshot_exige_versao_efetiva_correspondente() -> None:
    profile = valid_profile()
    digest = digest_strategy_document(b"contrato")

    def basis(version: str | None) -> StrategyBasis | None:
        return make_strategy_basis(
            profile,
            openapi_sha256=digest,
            data_rules_sha256=digest,
            flows_sha256=digest,
            engine_version=version,
        )

    original = basis("2.17")
    assert original is not None
    strategy = Strategy.from_data({**data(), "choices": [choice(basis=original.model_dump())]})
    plan = ScanPlan((), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    def compile_with(version: str | None) -> None:
        compile_scan_snapshot(
            profile,
            approval_for(profile),
            strategy,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=plan,
            proposed=plan,
            baseline_policy=policy,
            proposed_policy=policy,
            baseline_limits=limits,
            proposed_limits=limits,
            basis=basis(version),
        )

    compile_with("2.17")
    for version in (None, "2.18"):
        with pytest.raises(ConfigError):
            compile_with(version)


def test_oast_reduction_preserves_narrowed_snapshot_restrictions() -> None:
    from harness_dast.domain.scan_policy import without_oast

    profile = valid_profile()
    profile = profile.model_copy(update={"scan": profile.scan.model_copy(update={"oast": True})})
    plan = ScanPlan((), (), ())
    original = build_policy(profile.scan, experimental_rules=True)
    narrowed = original.model_copy(update={"disabled_rules": (*original.disabled_rules, 90001)})
    limits = build_limits(profile.limits, profile.scan)
    snapshot = compile_scan_snapshot(
        profile,
        approval_for(profile),
        None,
        datetime(2026, 11, 16, tzinfo=UTC),
        baseline=plan,
        proposed=plan,
        baseline_policy=narrowed,
        proposed_policy=narrowed,
        baseline_limits=limits,
        proposed_limits=limits,
    )

    reduced = without_oast(snapshot.policy)
    assert 90001 in reduced.disabled_rules
    assert 40046 in reduced.disabled_rules
    assert 40046 not in reduced.experimental_rules
