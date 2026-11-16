"""Aceite independente da preservação da varredura planejada."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from harness_dast.application.scan import Scan, ScanRequest
from harness_dast.application.scope_approval import ApprovedProfileRepository
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.scan_plan import ScanPlan, ScanTarget
from harness_dast.domain.scan_policy import build_limits, build_policy
from harness_dast.domain.scope_approval import ScopeApproval
from harness_dast.domain.strategy import StrategyReferences
from harness_dast.domain.strategy_plan import compile_scan_snapshot
from tests.fakes.approvals import InMemoryApprovalStore, approval_for
from tests.fakes.profile_data import valid_profile
from tests.fakes.rig import agenda_flows
from tests.fakes.scan_rig import ScanRig


class _StrategyStore:
    def __init__(self, present: bool) -> None:
        self.present = present

    def read(self, product: str) -> dict[str, object] | None:
        if not self.present:
            return None
        return {
            "schema_version": 1,
            "references": {
                "target": "target.yml",
                "data_rules": "data-rules.yml",
                "flows": "flows.yml",
            },
            "choices": [],
        }

    def check_references(self, product: str, references: StrategyReferences) -> None:
        pass

    def migrate(self, product: str, output: str) -> str:
        raise AssertionError("migração não deve ser chamada")


def _scan_com_estrategia(present: bool) -> tuple[object, object, object]:
    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    scan = Scan(
        profiles=rig.profiles,
        specs=rig._specs(),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        scanner=rig.scanner,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        strategy_store=_StrategyStore(present),
        approvals=approvals,
    )
    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))
    return result.entries, result.skipped, (rig.zap.started, rig.zap.applied)


def test_scan_real_com_falsos_preserva_trabalho_com_estrategia() -> None:
    baseline = _scan_com_estrategia(False)

    actual = _scan_com_estrategia(True)

    assert actual == baseline


def test_revogacao_durante_scan_interrompe_job_e_grava_resultado() -> None:
    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = InMemoryApprovalStore()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    rig.zap.script = [(10, "RUNNING"), (100, "FINISHED")]

    def revoke(scan_id: str, poll: int) -> None:
        if scan_id == "0" and poll == 0:
            approvals.items.clear()

    rig.zap.on_status = revoke
    scan = Scan(
        profiles=ApprovedProfileRepository(rig.profiles, approvals),
        specs=rig._specs(),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        scanner=rig.scanner,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        strategy_store=_StrategyStore(True),
        approvals=approvals,
    )

    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert len(rig.zap.started) == 1
    assert rig.zap.was_stopped("0") is True
    assert result.entries[0].outcome == "stopped"
    assert rig.artifacts.scans[probe.run_id] == result


def test_revogacao_apos_compilar_impede_inicio_do_job() -> None:
    class RevokedAfterCompilation(InMemoryApprovalStore):
        reads = 0

        def read(self, product: str) -> ScopeApproval | None:
            approval = super().read(product)
            self.reads += 1
            if self.reads == 2:
                self.items.clear()
            return approval

    rig = ScanRig(flows=agenda_flows())
    probe = rig.run_probe()
    approvals = RevokedAfterCompilation()
    approvals.write(approval_for(rig.profiles.load("agenda")))
    scan = Scan(
        profiles=ApprovedProfileRepository(rig.profiles, approvals),
        specs=rig._specs(),
        documents=rig.documents,
        secrets=rig.secrets,
        vault=rig.vault,
        client=rig.target,
        zap=rig.zap,
        scanner=rig.scanner,
        store=rig.store,
        artifacts=rig.artifacts,
        clock=rig.clock,
        sleeper=rig.clock,
        strategy_store=_StrategyStore(True),
        approvals=approvals,
    )

    result = scan.execute(ScanRequest(product="agenda", run_id=probe.run_id))

    assert result.status == "stopped_window"
    assert rig.zap.started == []
    assert rig.artifacts.scans[probe.run_id] == result


@pytest.mark.parametrize(
    "change",
    ["operation", "account", "path", "precondition"],
)
def test_recusa_alteracao_de_item_do_plano(change: str) -> None:
    profile = valid_profile()
    target = ScanTarget("operacao", "GET", "/item", 1, "https://example.test/item", None)
    baseline = ScanPlan((target,), (), ())
    alternatives = {
        "operation": replace(target, operation_id="outra-operacao"),
        "account": replace(target, account="outra-conta"),
        "path": replace(target, path="/outro-ponto"),
        "precondition": replace(target, seed_outcome="not_found"),
    }
    proposed = ScanPlan((alternatives[change],), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    with pytest.raises(ConfigError):
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


@pytest.mark.parametrize(
    "change",
    [{"strength": "HIGH"}, {"disabled_rules": (40018,)}, {"url_path_injection": False}],
)
def test_recusa_alteracao_de_politica_de_cobertura(change: dict[str, object]) -> None:
    profile = valid_profile()
    plan = ScanPlan((), (), ())
    policy = build_policy(profile.scan)
    limits = build_limits(profile.limits, profile.scan)

    with pytest.raises(ConfigError):
        compile_scan_snapshot(
            profile,
            approval_for(profile),
            None,
            datetime(2026, 11, 16, tzinfo=UTC),
            baseline=plan,
            proposed=plan,
            baseline_policy=policy,
            proposed_policy=policy.model_copy(update=change),
            baseline_limits=limits,
            proposed_limits=limits,
        )
