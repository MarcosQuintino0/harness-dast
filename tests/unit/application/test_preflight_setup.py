"""`preflight` e `probe.setup_path`: GET idempotente que prepara os dados antes dos logins."""

from typing import Any

import pytest

from harness_dast.application.preflight_report import PreflightReport
from harness_dast.domain.errors import ExternalToolError, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest
from tests.fakes.probe_ports import reply
from tests.fakes.rig import Rig, agenda_profile, default_handler, profile_data

SETUP = "/api/preparar"


def run(rig: Rig) -> PreflightReport:
    return rig.preflight().execute("agenda")


def by_id(report: PreflightReport) -> dict[str, Any]:
    return {check.id: check for check in report.checks}


def setup_rig(
    result: Any = None, *, probe: dict[str, Any] | None = None, zap_down: bool = False
) -> Rig:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "preflight.setup" and result is not None:
            return result
        if request.operation_id in {"preflight.setup", "preflight.health"}:
            return reply(200, {"ok": True})
        return default_handler(request, jar)

    declared = {"health_path": "/api/saude", "setup_path": SETUP} if probe is None else probe
    rig = Rig(profile=agenda_profile(probe=declared), handler=handler)
    if zap_down:
        rig.zap.fail = ExternalToolError("sem resposta", hint="suba o ZAP")
    return rig


def test_setup_path_is_called_once_with_get_after_health_and_before_every_login() -> None:
    rig = setup_rig()

    report = run(rig)

    assert report.ready is True
    assert [c.id for c in report.checks] == [
        "authorization",
        "window",
        "secrets:user_a",
        "zap",
        "target_health",
        "target_setup",
        "login:user_a",
    ]
    assert [r.operation_id for r in rig.target.requests] == [
        "preflight.health",
        "preflight.setup",
        "auth.login",
    ]
    setup = rig.target.requests[1]
    assert setup.method == "GET"
    assert setup.url.endswith(SETUP)
    assert setup.route == "zap"
    assert setup.account is None


def test_setup_request_goes_through_the_audit_trail() -> None:
    rig = setup_rig()

    report = run(rig)

    assert report.run_id is not None
    operations = [e.operation_id for e in rig.store.audit[report.run_id] if e.phase == "decision"]
    assert operations == ["preflight.health", "preflight.setup", "auth.login"]


def test_nothing_is_called_for_setup_when_the_profile_does_not_declare_it() -> None:
    rig = setup_rig(probe={"health_path": "/api/saude"})

    report = run(rig)

    assert "target_setup" not in by_id(report)
    assert all(r.operation_id != "preflight.setup" for r in rig.target.requests)


def test_health_path_still_works_as_the_old_seeding_trick() -> None:
    rig = setup_rig(probe={"health_path": SETUP})

    report = run(rig)

    assert report.ready is True
    assert rig.target.requests[0].url.endswith(SETUP)


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(reply(404, {}), id="not_found"),
        pytest.param(reply(401, {}), id="unauthorized"),
        pytest.param(reply(500, {}), id="server_error"),
        pytest.param(TargetTimeout("lento"), id="timeout"),
    ],
)
def test_setup_failure_makes_the_report_not_ready(result: Any) -> None:
    report = run(setup_rig(result))

    check = by_id(report)["target_setup"]
    assert report.ready is False
    assert check.ok is False
    assert check.kind == "environment"


def test_setup_http_error_detail_tells_which_field_to_check() -> None:
    check = by_id(run(setup_rig(reply(404, {}))))["target_setup"]

    assert "probe.setup_path" in check.detail
    assert "404" in check.detail


def test_setup_is_not_run_when_the_zap_is_down() -> None:
    rig = setup_rig(zap_down=True)

    check = by_id(run(rig))["target_setup"]

    assert check.ok is False
    assert "Não executado" in check.detail
    assert all(r.operation_id != "preflight.setup" for r in rig.target.requests)


def test_setup_is_not_called_when_authorization_is_expired() -> None:
    data = profile_data()
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    rig = Rig(profile=agenda_profile(scope=data["scope"], probe={"setup_path": SETUP}))

    report = run(rig)

    assert report.ready is False
    assert rig.target.requests == []


def test_login_without_token_hint_points_to_setup_path() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"status": "fail"})
        return reply(200, {})

    check = by_id(run(Rig(handler=handler)))["login:user_a"]

    assert check.ok is False
    assert "probe.setup_path" in check.detail
    assert "probe.health_path" not in check.detail
