"""Caso de uso `scan` com falsos: plano, limites, política, contexto e artefatos."""

import copy
from typing import Any

import pytest

from harness_dast.application.scan import ScanRequest
from harness_dast.domain.errors import ConfigError, PreflightError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_policy import DEFAULT_DISABLED_RULES
from tests.fakes.rig import PASSWORD, TOKEN, agenda_flows, agenda_profile, profile_data
from tests.fakes.scan_rig import ScanRig
from tests.fakes.zap_alerts import attack_message, zap_alert


def ready(*, flows: bool = True, probe: dict[str, Any] | None = None, **kwargs: Any) -> ScanRig:
    rig = ScanRig(flows=agenda_flows() if flows else None, **kwargs)
    rig.run_probe(**(probe or {}))
    return rig


def with_scan(**scan: Any) -> Any:
    return agenda_profile(scan=scan)


def test_scans_only_successful_safe_operations_one_scan_per_learned_request() -> None:
    rig = ready()

    result = rig.run_scan()

    assert result.status == "completed"
    assert [e.operation_id for e in result.entries] == ["listar", "buscar", "criar", "atualizar"]
    assert [s.method for s in rig.zap.started] == ["GET", "GET", "POST", "PUT"]
    skipped = {s.operation_id: s.reason for s in result.skipped}
    assert skipped == {
        "login": "login",
        "admin": "not_success",
        "externo": "not_success",
        "remover": "not_success",
    }


def test_delete_is_never_scanned_even_when_the_probe_deleted_with_success() -> None:
    rig = ready(probe={"include_delete": True})

    result = rig.run_scan()

    assert "remover" not in [e.operation_id for e in result.entries]
    assert {s.operation_id: s.reason for s in result.skipped}["remover"] == "delete"
    assert "DELETE" not in [s.method for s in rig.zap.started]


def test_denied_and_out_of_scope_operations_are_never_planned() -> None:
    rig = ready()

    result = rig.run_scan()

    names = {s.operation_id for s in result.skipped}
    assert {"admin", "externo"} <= names
    assert all("admin" not in r.url and "outra" not in r.url for r in rig.zap.started)


def test_a_url_learned_by_zap_outside_the_scope_is_dropped_by_the_guard() -> None:
    rig = ready()
    # O ZAP aprendeu, para o mesmo método e caminho, uma URL de OUTRO host.
    for number, message in list(rig.zap.messages.items()):
        rig.zap.messages[number] = message.model_copy(
            update={
                "request_header": message.request_header.replace(
                    "api.hml.acme-teste.net.br", "outro.exemplo.com"
                )
            }
        )

    result = rig.run_scan()

    assert result.entries == ()
    assert {s.reason for s in result.skipped if s.operation_id == "listar"} == {"scope"}
    assert rig.zap.started == []


def test_a_denied_path_learned_by_zap_is_dropped_by_the_guard() -> None:
    rig = ready()
    message = rig.zap.messages[2]
    rig.zap.messages[2] = message.model_copy(
        update={
            "request_header": message.request_header.replace(
                "/api/pacientes", "/api/admin/usuarios"
            )
        }
    )

    result = rig.run_scan(only=("listar",))

    assert result.entries == ()
    assert rig.zap.started == []


def test_put_runs_only_on_resources_created_by_the_run_or_with_profile_opt_in() -> None:
    created = ready(flows=True).run_scan()
    unlinked = ready(flows=False).run_scan()
    opted_in = ready(flows=False, profile=with_scan(mutating_methods=["PUT"])).run_scan()

    assert "atualizar" in [e.operation_id for e in created.entries]
    assert "atualizar" not in [e.operation_id for e in unlinked.entries]
    assert {s.operation_id: s.reason for s in unlinked.skipped}["atualizar"] == "mutating"
    assert "atualizar" in [e.operation_id for e in opted_in.entries]


def test_read_operations_run_before_writes_so_a_deadline_cuts_the_riskiest_last() -> None:
    rig = ready()

    result = rig.run_scan()

    methods = [e.method for e in result.entries]
    assert methods == sorted(methods, key=["GET", "POST", "PUT"].index)


def test_only_narrows_the_selection() -> None:
    rig = ready()

    result = rig.run_scan(only=("buscar",))

    assert [e.operation_id for e in result.entries] == ["buscar"]
    assert {s.operation_id: s.reason for s in result.skipped}["listar"] == "not_selected"


def test_extra_outcomes_can_be_included_but_only_from_a_closed_list() -> None:
    rig = ready()

    with pytest.raises(ConfigError, match="include-outcome"):
        rig.run_scan(include_outcomes=("server_error",))


def test_limits_and_policy_are_applied_before_the_first_scan_and_context_is_always_sent() -> None:
    rig = ready()

    result = rig.run_scan()

    calls = rig.zap.calls
    assert calls.index("apply_policy") < next(
        i for i, c in enumerate(calls) if c.startswith("start")
    )
    policy, limits = rig.zap.applied[0]
    assert (limits.threads_per_host, limits.delay_ms) == (2, 200)
    assert policy.url_path_injection is True
    assert policy.injectable_mask == 51
    assert set(policy.disabled_rules) >= {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}
    context_id = rig.artifacts.read_manifest(result.run_id).zap_context_id
    assert context_id is not None
    assert {request.context_id for request in rig.zap.started} == {context_id}
    assert {request.policy_name for request in rig.zap.started} == {policy.name}


def test_profile_can_add_disabled_rules_and_turn_path_injection_off_but_not_enable_defaults() -> (
    None
):
    rig = ready(
        profile=with_scan(disable_rules=[90001], url_path_injection=False, strength="MEDIUM")
    )

    rig.run_scan()

    policy, _ = rig.zap.applied[0]
    assert 90001 in policy.disabled_rules
    assert policy.injectable_mask == 35
    assert policy.strength == "MEDIUM"
    assert {r.plugin_id for r in DEFAULT_DISABLED_RULES} <= set(policy.disabled_rules)


def test_flags_only_reduce_limits() -> None:
    rig = ready()

    result = rig.run_scan(threads=1, max_minutes=30)

    assert (result.limits.threads_per_host, result.limits.max_duration_minutes) == (1, 30)
    with pytest.raises(ConfigError):
        rig.run_scan(threads=8)
    with pytest.raises(ConfigError):
        rig.run_scan(max_minutes=61)
    with pytest.raises(ConfigError, match="intervalo"):
        rig.run_scan(threads=0)


def test_each_scan_gets_a_cap_no_larger_than_the_profile_and_the_remaining_time() -> None:
    rig = ready(profile=with_scan(max_scan_minutes=5))

    rig.run_scan(max_minutes=3)

    assert {r.max_scan_minutes for r in rig.zap.started} == {3}


def test_dry_run_shows_the_plan_and_touches_neither_zap_nor_target_nor_disk() -> None:
    rig = ready()
    before = (
        len(rig.target.requests),
        len(rig.zap.calls),
        len(rig.store.audit["x"]) if "x" in rig.store.audit else 0,
    )
    calls_before = list(rig.zap.calls)
    sent_before = len(rig.target.requests)

    result = rig.run_scan(dry_run=True)

    assert result.dry_run is True
    assert [p.operation_id for p in result.planned] == ["listar", "buscar", "criar", "atualizar"]
    assert rig.zap.calls == calls_before
    assert len(rig.target.requests) == sent_before
    assert rig.artifacts.scans == {}
    assert rig.artifacts.progress == {}
    assert before[0] == sent_before


def test_unknown_or_unusable_runs_are_configuration_errors() -> None:
    rig = ready()
    rig.store.probes[rig.probe_result.run_id] = rig.probe_result.model_copy(
        update={"dry_run": True}
    )

    with pytest.raises(ConfigError, match="dry-run"):
        rig.run_scan()
    other = "2026-11-10T11-00-00Z-agenda-aaaa"
    with pytest.raises(ConfigError):
        rig.scan().execute(ScanRequest(product="agenda", run_id=other))
    with pytest.raises(ConfigError, match="inválido"):
        rig.scan().execute(ScanRequest(product="agenda", run_id="../../etc"))


def test_a_run_of_another_product_is_refused() -> None:
    rig = ready()
    run_id = rig.probe_result.run_id
    rig.store.probes[run_id] = rig.store.probes[run_id].model_copy(update={"product": "outro"})

    with pytest.raises(ConfigError, match="outro produto"):
        rig.run_scan()


def test_missing_zap_context_is_a_preflight_error_and_nothing_is_scanned() -> None:
    rig = ready()
    rig.zap.context = None

    with pytest.raises(PreflightError, match="ZAP"):
        rig.run_scan()

    assert rig.zap.started == []
    assert rig.zap.installed == {}


def test_policy_that_leaves_a_rule_enabled_stops_before_any_scan_and_removes_the_rules() -> None:
    rig = ready()
    rig.zap.ignore_disable = True

    with pytest.raises(PreflightError, match="continuam ligadas"):
        rig.run_scan()

    assert rig.zap.started == []
    assert rig.zap.installed == {}


def test_a_scan_the_zap_refuses_is_recorded_and_the_others_continue() -> None:
    rig = ready()
    rig.zap.refuse = frozenset({"POST"})

    result = rig.run_scan()

    assert {e.operation_id: e.outcome for e in result.entries}["criar"] == "refused"
    assert result.status == "completed"
    assert [e.outcome for e in result.entries if e.operation_id == "listar"] == ["completed"]


def test_truncated_scan_is_detected_by_progress_below_100_and_reported() -> None:
    rig = ready()
    rig.zap.script = [(45, "FINISHED")]

    result = rig.run_scan()

    assert result.status == "completed"
    assert all(
        e.truncated and e.outcome == "truncated" and e.progress == 45 for e in result.entries
    )
    assert "parcial" in (result.entries[0].note or "")


def test_alerts_are_attributed_to_the_scan_that_raised_them() -> None:
    rig = ready()
    rig.zap.alert_factory = lambda request, zap: (
        [zap_alert(sourceMessageId="999", messageId="1604")] if request.method == "POST" else []
    )

    result = rig.run_scan()

    entry = {e.operation_id: e for e in result.entries}["criar"]
    assert entry.alert_ids == ("1",)
    assert entry.alert_count == 1
    assert result.alerts_total == 1
    assert result.alerts_by_risk == {"high": 1}


def test_alerts_and_evidence_are_redacted_before_they_are_written() -> None:
    rig = ready()
    rig.zap.messages[1604] = attack_message(1604, token=TOKEN, body=f'{{"password": "{PASSWORD}"}}')
    rig.zap.alert_factory = lambda request, zap: (
        [zap_alert(evidence=f"Authorization: Bearer {TOKEN}", attack=PASSWORD)]
        if request.method == "POST"
        else []
    )

    rig.run_scan()

    written = rig.artifacts.serialized() + rig.store.serialized()
    assert TOKEN not in written
    assert PASSWORD not in written
    assert rig.artifacts.evidence[rig.probe_result.run_id][0].message_id == 1604


def test_scan_audit_continues_the_probe_numbering_and_never_logs_the_token() -> None:
    rig = ready()
    run_id = rig.probe_result.run_id
    before = max(entry.seq for entry in rig.store.audit[run_id])

    rig.run_scan()

    after = [entry.seq for entry in rig.store.audit[run_id] if entry.seq > before]
    assert after
    assert before + 1 == min(after)
    assert TOKEN not in rig.store.serialized()


def test_progress_file_follows_the_phases_and_ends_done() -> None:
    rig = ready()

    result = rig.run_scan()

    steps = rig.artifacts.progress[result.run_id]
    assert steps[0].phase == "starting"
    assert {p.phase for p in steps} >= {"scanning", "collecting", "done"}
    assert steps[-1].phase == "done"
    assert steps[-1].status == "completed"
    assert max(p.index for p in steps) == 4


def test_default_policy_matches_the_documented_values() -> None:
    profile = agenda_profile()

    assert (profile.scan.strength, profile.scan.threshold) == ("LOW", "MEDIUM")
    assert profile.scan.url_path_injection is True
    assert profile.scan.fail_on == "none"


def test_scan_block_rejects_unknown_fields_and_values_outside_the_closed_sets() -> None:
    for bad in ({"strength": "INSANE"}, {"mutating_methods": ["DELETE"]}, {"turbo": True}):
        data = copy.deepcopy(profile_data(scan=bad))
        with pytest.raises(ConfigError):
            ProductProfile.from_data(data)


def test_only_with_an_operation_the_run_does_not_have_is_a_configuration_error() -> None:
    rig = ready()

    with pytest.raises(ConfigError, match=r"operação desconhecida.*inexistente"):
        rig.run_scan(only=("inexistente",))

    assert rig.zap.started == []
