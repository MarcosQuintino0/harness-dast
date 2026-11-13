"""`scan`: janela, prazo, saúde do alvo, falha do ZAP, Ctrl+C e a remoção das regras."""

from datetime import timedelta
from typing import Any

import pytest

from harness_dast.application.scan_health import FAILURE_LIMIT, RECOVERY_WAIT_SECONDS
from harness_dast.domain.errors import (
    ExternalToolError,
    TargetUnreachable,
)
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import reply
from tests.fakes.rig import agenda_flows, default_handler, profile_data
from tests.fakes.scan_rig import ScanRig


def ready(profile: ProductProfile | None = None, **kwargs: Any) -> ScanRig:
    rig = ScanRig(flows=agenda_flows(), profile=profile, **kwargs)
    rig.run_probe()
    return rig


def profile_with(**changes: Any) -> ProductProfile:
    data = profile_data()
    for key, value in changes.items():
        data[key] = {**data.get(key, {}), **value} if isinstance(value, dict) else value
    return ProductProfile.from_data(data)


def test_window_closing_mid_scan_stops_the_scan_and_keeps_partial_results() -> None:
    scope = profile_data()["scope"] | {"windows": ["seg-dom 00:00-12:30 UTC"]}
    rig = ready(profile_with(scope=scope))
    rig.zap.script = [(10, "RUNNING"), (20, "RUNNING"), (100, "FINISHED")]
    first = {"done": False}

    def close_after_first_scan(scan_id: str, poll: int) -> None:
        if scan_id == "1" and poll == 0 and not first["done"]:
            first["done"] = True
            rig.clock.advance(31 * 60)

    rig.zap.on_status = close_after_first_scan

    result = rig.run_scan()

    assert result.status == "stopped_window"
    assert [e.operation_id for e in result.entries] == ["listar", "criar"]
    assert [e.outcome for e in result.entries] == ["completed", "stopped"]
    assert rig.zap.was_stopped("1") is True
    pending = {s.operation_id: s.reason for s in result.skipped}
    assert pending["buscar"] == "not_run"
    assert rig.artifacts.scans[result.run_id] == result
    assert rig.zap.installed == {}


def test_deadline_passing_mid_scan_stops_it_and_stores_the_partial_result() -> None:
    rig = ready(profile_with(limits={"max_duration_minutes": 1}))
    rig.zap.script = [(10, "RUNNING")]

    result = rig.run_scan()

    assert result.status == "stopped_deadline"
    assert result.entries[-1].outcome == "stopped"
    assert rig.artifacts.scans[result.run_id].status == "stopped_deadline"
    assert rig.zap.installed == {}
    assert "stop_scan" in rig.zap.calls


def test_target_that_stops_answering_ends_the_scan_before_the_next_scan() -> None:
    rig = ready()
    down = TargetUnreachable("fora do ar")
    rig.target._handler = lambda request, jar: (
        down if request.operation_id == "scan.health" else default_handler(request, jar)
    )

    result = rig.run_scan()

    assert result.status == "stopped_target_unresponsive"
    assert result.entries == ()
    assert rig.zap.started == []
    assert result.health.failures == FAILURE_LIMIT
    assert rig.clock.sleeps.count(RECOVERY_WAIT_SECONDS) == FAILURE_LIMIT - 1
    assert rig.zap.installed == {}


def test_a_target_that_recovers_in_time_lets_the_scan_continue() -> None:
    rig = ready()
    attempts = {"n": 0}

    def flaky(request: Any, jar: dict[str, str]) -> Any:
        if request.operation_id == "scan.health":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return reply(503, {"detail": "ocupado"})
        return default_handler(request, jar)

    rig.target._handler = flaky

    result = rig.run_scan()

    assert result.status == "completed"
    assert result.health.failures == 1
    assert result.health.checks > 1


def test_health_check_is_disabled_when_no_health_path_is_in_scope() -> None:
    data = profile_data()
    del data["probe"]
    rig = ready(ProductProfile.from_data(data))

    result = rig.run_scan()

    assert result.health.enabled is False
    assert result.status == "completed"


def test_zap_failure_mid_scan_stops_with_stopped_zap_and_still_removes_the_rules() -> None:
    rig = ready()
    rig.zap.failures = {"scan_status": ExternalToolError("O ZAP caiu.")}

    result = rig.run_scan()

    assert result.status == "stopped_zap"
    assert result.stop_message == "O ZAP caiu."
    assert result.alerts_total == 0
    assert rig.zap.installed == {}
    assert rig.artifacts.scans[result.run_id].status == "stopped_zap"


def test_failure_collecting_alerts_turns_a_completed_scan_into_stopped_zap() -> None:
    rig = ready()
    rig.zap.failures = {"list_alerts": ExternalToolError("sem alertas")}

    result = rig.run_scan()

    assert result.status == "stopped_zap"
    assert "coletar" in (result.stop_message or "")


def test_ctrl_c_stops_the_running_scan_and_removes_the_rules() -> None:
    rig = ready()

    def interrupt(scan_id: str, poll: int) -> None:
        raise KeyboardInterrupt

    rig.zap.on_status = interrupt

    with pytest.raises(KeyboardInterrupt):
        rig.run_scan()

    assert rig.zap.installed == {}
    assert rig.zap.was_stopped("0") is True
    last = rig.artifacts.progress[rig.probe_result.run_id][-1]
    assert last.status == "interrupted"


def test_failing_to_remove_the_rules_at_the_end_is_an_error_after_saving_the_result() -> None:
    rig = ready()
    rig.zap.failures = {"remove_stale_rules": ExternalToolError("sem resposta")}
    rig.zap.let_through = {"remove_stale_rules": 1}

    with pytest.raises(ExternalToolError, match="Replacer"):
        rig.run_scan()

    saved = rig.artifacts.scans[rig.probe_result.run_id]
    assert saved.rules_removed is False


def test_a_login_refused_in_the_middle_ends_the_scan_with_stopped_auth() -> None:
    profile = profile_with(scan={"token_refresh_seconds": 10})
    rig = ready(profile)
    rig.zap.script = [(10, "RUNNING")] * 6 + [(100, "FINISHED")]
    rig.target._handler = lambda request, jar: (
        reply(401, {"detail": "negado"})
        if request.operation_id == "auth.login" and rig.zap.started
        else default_handler(request, jar)
    )

    result = rig.run_scan()

    assert result.status == "stopped_auth"
    assert rig.zap.installed == {}


def test_deadline_is_total_across_scans_not_per_scan() -> None:
    rig = ready(profile_with(limits={"max_duration_minutes": 1}))
    rig.zap.script = [(100, "FINISHED")]

    def slow(scan_id: str, poll: int) -> None:
        rig.clock.advance(timedelta(minutes=0.4).total_seconds())

    rig.zap.on_status = slow

    result = rig.run_scan()

    assert result.status == "stopped_deadline"
    assert len(result.entries) < 4
