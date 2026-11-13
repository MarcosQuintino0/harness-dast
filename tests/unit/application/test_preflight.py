"""Caso de uso `preflight`: lista de verificações como dado, sem vazar segredo."""

import json
from typing import Any

import pytest

from harness_dast.application.preflight_report import PreflightReport
from harness_dast.domain.errors import ConfigError, ExternalToolError, TargetTimeout
from harness_dast.domain.http_messages import HttpRequest
from tests.fakes.probe_ports import reply
from tests.fakes.rig import (
    LOGIN,
    PASSWORD,
    TOKEN,
    Rig,
    agenda_profile,
    default_handler,
    profile_data,
)


def run(rig: Rig) -> PreflightReport:
    return rig.preflight().execute("agenda")


def by_id(report: PreflightReport) -> dict[str, Any]:
    return {check.id: check for check in report.checks}


def test_everything_ok_gives_a_ready_report_with_one_check_per_item() -> None:
    rig = Rig()

    report = run(rig)

    assert report.ready is True
    assert [c.id for c in report.checks] == [
        "authorization",
        "window",
        "secrets:user_a",
        "zap",
        "target_health",
        "login:user_a",
    ]
    assert all(c.ok for c in report.checks)
    assert report.zap_version == "2.17.0"
    assert report.run_id == "2026-11-10T12-00-00Z-agenda-7f3a"


def test_preflight_uses_the_same_guarded_path_and_audits_each_request() -> None:
    rig = Rig()

    report = run(rig)

    assert report.run_id is not None
    operations = [e.operation_id for e in rig.store.audit[report.run_id] if e.phase == "decision"]
    assert operations == ["preflight.health", "auth.login"]
    assert rig.store.manifests[report.run_id][-1].command == "preflight"
    assert rig.store.manifests[report.run_id][-1].status == "ready"


def test_the_health_check_uses_the_profile_health_path() -> None:
    profile = agenda_profile(probe={"health_path": "/api/saude"})
    rig = Rig(profile=profile)

    run(rig)

    health = rig.target.requests[0]
    assert health.url.endswith("/api/saude")
    assert health.method == "GET"
    assert health.route == "zap"


def test_an_expired_authorization_is_a_scope_failure_and_nothing_is_sent() -> None:
    data = profile_data()
    data["scope"]["authorization"]["valid_until"] = "2020-01-01"
    rig = Rig(profile=agenda_profile(scope=data["scope"]))

    report = run(rig)

    checks = by_id(report)
    assert report.ready is False
    assert checks["authorization"].ok is False
    assert checks["authorization"].kind == "scope"
    assert "expirou" in checks["authorization"].detail
    assert checks["zap"].ok is False
    assert rig.target.requests == []
    assert rig.store.events == []
    failure = report.first_failure()
    assert failure is not None
    assert failure.kind == "scope"


def test_a_closed_window_is_a_scope_failure() -> None:
    data = profile_data()
    data["scope"]["windows"] = ["seg-dom 20:00-21:00 UTC"]

    report = run(Rig(profile=agenda_profile(scope=data["scope"])))

    assert by_id(report)["window"].ok is False
    assert by_id(report)["window"].kind == "scope"


def test_missing_secret_names_account_and_field_and_hides_the_variable_name_from_json() -> None:
    rig = Rig(env={"ACME_USER_A_LOGIN": LOGIN})

    report = run(rig)

    check = by_id(report)["secrets:user_a"]
    assert check.ok is False
    assert "user_a.password" in check.detail
    assert "ACME_USER_A_SENHA" not in check.detail
    assert "ACME_USER_A_SENHA" in (check.operator_detail or "")
    dumped = json.dumps(report.model_dump(mode="json"))
    assert "ACME_USER_A_SENHA" not in dumped
    assert "operator_detail" not in dumped
    assert by_id(report)["login:user_a"].ok is False
    assert all(r.operation_id != "auth.login" for r in rig.target.requests)


def test_zap_down_fails_zap_and_health_but_still_checks_the_login() -> None:
    rig = Rig()
    rig.zap.fail = ExternalToolError("sem resposta", hint="suba o ZAP")

    report = run(rig)

    checks = by_id(report)
    assert checks["zap"].ok is False
    assert "suba o ZAP" in checks["zap"].detail
    assert checks["target_health"].ok is False
    assert "Não executado" in checks["target_health"].detail
    assert checks["login:user_a"].ok is True
    assert report.zap_version is None
    assert report.ready is False


def test_an_untested_zap_version_is_accepted_with_a_warning() -> None:
    rig = Rig()
    rig.zap._version = "2.15.0"

    check = by_id(run(rig))["zap"]

    assert check.ok is True
    assert "validada" in check.detail


@pytest.mark.parametrize(
    ("result", "ok"),
    [
        (reply(200, {}), True),
        (reply(404, {}), True),
        (reply(401, {}), True),
        (reply(500, {}), False),
        (TargetTimeout("lento"), False),
    ],
)
def test_target_health_means_the_target_answered_without_a_server_error(
    result: Any, ok: bool
) -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "preflight.health":
            return result
        return default_handler(request, jar)

    assert by_id(run(Rig(handler=handler)))["target_health"].ok is ok


def test_without_a_health_path_the_root_outside_the_scope_tells_which_field_to_declare() -> None:
    report = run(Rig(profile=agenda_profile(probe={})))

    check = by_id(report)["target_health"]
    assert check.ok is False
    assert check.kind == "environment"
    assert "probe.health_path" in check.detail


def test_a_rejected_login_is_reported_without_the_credentials() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(401, {"detail": "no"})
        return reply(200, {})

    report = run(Rig(handler=handler))

    check = by_id(report)["login:user_a"]
    assert check.ok is False
    assert PASSWORD not in json.dumps(report.model_dump(mode="json"))
    assert report.ready is False


def test_login_token_is_never_part_of_the_report() -> None:
    report = run(Rig())

    assert TOKEN not in json.dumps(report.model_dump(mode="json"))
    assert PASSWORD not in json.dumps(report.model_dump(mode="json"))


def test_csrf_token_must_be_fetchable_when_the_profile_declares_it() -> None:
    profile = agenda_profile(auth={**profile_data()["auth"], "csrf": {"fetch_path": "/api/csrf"}})

    def no_cookie(request: HttpRequest, jar: dict[str, str]) -> Any:
        return default_handler(request, jar)

    failing = by_id(run(Rig(profile=profile, handler=no_cookie)))["csrf:user_a"]
    assert failing.ok is False

    def with_cookie(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.csrf":
            jar["XSRF-TOKEN"] = "abc"
            return reply(200, {})
        return default_handler(request, jar)

    report = run(Rig(profile=profile, handler=with_cookie))
    assert by_id(report)["csrf:user_a"].ok is True
    assert [c.id for c in report.checks].index("csrf:user_a") < [c.id for c in report.checks].index(
        "login:user_a"
    )


def test_each_account_is_checked() -> None:
    auth = profile_data()["auth"]
    auth["accounts"].append(
        {
            "alias": "admin_a",
            "role": "admin",
            "username": {"secret_ref": "env:ACME_ADMIN_LOGIN"},
            "password": {"secret_ref": "env:ACME_ADMIN_SENHA"},
        }
    )
    rig = Rig(
        profile=agenda_profile(auth=auth),
        env={
            "ACME_USER_A_LOGIN": LOGIN,
            "ACME_USER_A_SENHA": PASSWORD,
            "ACME_ADMIN_LOGIN": "root",
            "ACME_ADMIN_SENHA": "outra-senha-secreta",
        },
    )

    report = run(rig)

    ids = [c.id for c in report.checks]
    assert "login:user_a" in ids
    assert "login:admin_a" in ids
    assert "secrets:admin_a" in ids
    assert report.ready is True


def test_api_key_accounts_have_a_secret_check_and_no_login_check() -> None:
    auth = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [{"alias": "svc", "role": "s", "api_key": {"secret_ref": "env:ACME_K"}}],
    }
    rig = Rig(profile=agenda_profile(auth=auth), env={"ACME_K": "k" * 12})

    report = run(rig)

    ids = [c.id for c in report.checks]
    assert "secrets:svc" in ids
    assert not [i for i in ids if i.startswith("login:")]
    assert report.ready is True


def test_unknown_product_is_a_config_error() -> None:
    with pytest.raises(ConfigError):
        Rig().preflight().execute("nao-existe")
