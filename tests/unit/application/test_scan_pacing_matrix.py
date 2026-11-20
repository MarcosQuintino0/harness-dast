"""Equivalência do trabalho planejado para os dois ritmos, sem tráfego real."""

from typing import Literal

from harness_dast.domain.probe_plan import plan_probe
from harness_dast.domain.scan_config import ScanConfig
from tests.fakes.rig import agenda_flows, agenda_spec
from tests.fakes.scan_rig import ScanRig
from tests.unit.application.test_scan_accounts import ACCOUNTS_ENV, profile


def _rig(pacing: Literal["legacy", "proxy"], *, flows: bool = True) -> ScanRig:
    base = profile(account_map=[{"account": "user_b", "operations": ["criar", "atualizar"]}])
    config = ScanConfig(pacing=pacing, strength="HIGH", disable_rules=(40019,))
    rig = ScanRig(
        profile=base.model_copy(update={"scan": config}),
        spec=agenda_spec(),
        flows=agenda_flows() if flows else None,
        env=ACCOUNTS_ENV,
    )
    rig.run_probe()
    return rig


def test_pacing_matrix_matches_each_operation_account_input_rule_and_precondition() -> None:
    a, b = _rig("legacy"), _rig("proxy")
    pa, pb = a.profiles.load("agenda"), b.profiles.load("agenda")
    plan_a = plan_probe(
        a.spec, a.documents.load_flows("agenda"), pa.guard(), pa.environment.base_url
    )
    plan_b = plan_probe(
        b.spec, b.documents.load_flows("agenda"), pb.guard(), pb.environment.base_url
    )
    ra, rb = a.run_scan(), b.run_scan()

    assert pa.scope == pb.scope
    assert pa.auth == pb.auth
    assert pa.limits == pb.limits
    assert pa.scan.model_copy(update={"pacing": "proxy"}) == pb.scan
    assert len(plan_a) == len(plan_b)
    for left, right in zip(plan_a, plan_b, strict=True):
        assert left == right
        assert left.operation_id == right.operation_id
        assert left.decision == right.decision
        assert left.depends_on == right.depends_on
    assert next(item for item in plan_a if item.operation_id == "atualizar").depends_on == (
        "criar",
    )
    assert [op.outcome for op in a.probe_result.operations] == [
        op.outcome for op in b.probe_result.operations
    ]
    assert ra.skipped == rb.skipped
    assert ra.policy == rb.policy
    assert ra.policy.strength == "HIGH"
    assert 40019 in ra.policy.disabled_rules
    assert ra.policy.injectable_mask == 51
    assert ra.limits.model_copy(update={"delay_ms": 0}) == rb.limits
    assert ra.limits.delay_ms > 0
    assert rb.limits.delay_ms == 0

    assert len(ra.entries) == len(rb.entries) == 4
    accounts = []
    for left, right, request_a, request_b, auth_a, auth_b in zip(
        ra.entries,
        rb.entries,
        a.zap.started,
        b.zap.started,
        a.zap.rules_at_start,
        b.zap.rules_at_start,
        strict=True,
    ):
        assert (left.operation_id, left.method, left.path, left.seed_outcome) == (
            right.operation_id,
            right.method,
            right.path,
            right.seed_outcome,
        )
        assert (request_a.method, request_a.url, request_a.body) == (
            request_b.method,
            request_b.url,
            request_b.body,
        )
        assert auth_a == auth_b
        accounts.extend(auth_a)
    assert any("user_a" in account for account in accounts)
    assert any("user_b" in account for account in accounts)
    assert [entry.operation_id for entry in ra.entries] == [
        "listar",
        "buscar",
        "criar",
        "atualizar",
    ]
    assert ["user_a" in row[0] for row in a.zap.rules_at_start] == [True, True, False, False]
    stats_a = a.artifacts.read_rule_stats(ra.run_id)
    stats_b = b.artifacts.read_rule_stats(rb.run_id)
    assert stats_a is not None
    assert stats_b is not None
    assert len(stats_a.operations) == len(stats_b.operations) == 4
    for rules_a, rules_b in zip(stats_a.operations, stats_b.operations, strict=True):
        assert rules_a.operation_id == rules_b.operation_id
        assert rules_a.unavailable_reason == rules_b.unavailable_reason
        assert rules_a.rules == rules_b.rules


def test_pacing_does_not_authorize_mutation_without_created_resource() -> None:
    a, b = _rig("legacy", flows=False), _rig("proxy", flows=False)

    ra, rb = a.run_scan(), b.run_scan()

    assert ra.planned == rb.planned
    assert ra.skipped == rb.skipped
    assert {item.operation_id: item.reason for item in ra.skipped}["atualizar"] == "mutating"
