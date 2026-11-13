"""Entrega do token ao ZAP: instalação, renovação (adiciona antes de remover), CSRF e limpeza."""

from typing import Any

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.zap_scope import REPLACER_RULE_PREFIX
from tests.fakes.probe_ports import reply
from tests.fakes.rig import TOKEN, agenda_flows, default_handler, profile_data
from tests.fakes.scan_rig import ScanRig

CSRF_VALUE = "csrf-VALOR-0123456789"


def csrf_handler(request: Any, jar: dict[str, str]) -> Any:
    path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
    if request.method == "GET" and path == "api/csrf":
        jar["XSRF-TOKEN"] = CSRF_VALUE
        return reply(200, {})
    return default_handler(request, jar)


def ready(*, csrf: bool = False, refresh: int | None = None) -> ScanRig:
    data = profile_data()
    if csrf:
        data["auth"]["csrf"] = {"fetch_path": "/api/csrf"}
    if refresh is not None:
        data["scan"] = {"token_refresh_seconds": refresh}
    rig = ScanRig(
        flows=agenda_flows(),
        profile=ProductProfile.from_data(data),
        **({"handler": csrf_handler} if csrf else {}),
    )
    rig.run_probe()
    return rig


def test_the_auth_header_rule_is_installed_before_the_first_scan() -> None:
    rig = ready()

    rig.run_scan()

    assert rig.zap.rules_at_start[0] == [f"{REPLACER_RULE_PREFIX}auth-user_a-1-1"]
    first = next(r for r in rig.zap.rule_log if r[0] == "add")
    assert first[1].startswith(REPLACER_RULE_PREFIX)


def test_the_installed_rule_overrides_authorization_for_the_target_origin_only() -> None:
    rig = ready()

    rig.run_scan()

    rule = rig.zap.ever_installed[f"{REPLACER_RULE_PREFIX}auth-user_a-1-1"]
    assert (rule.match_type, rule.match_string, rule.regex) == (
        "REQ_HEADER",
        "Authorization",
        False,
    )
    assert rule.replacement == f"Bearer {TOKEN}"
    assert rule.url.startswith(r"^https://api\.hml\.")
    assert rule.url.endswith("(?::443)?/.*")
    assert TOKEN not in repr(rule)


def test_the_token_is_refreshed_by_adding_the_new_rules_before_removing_the_old_ones() -> None:
    rig = ready(refresh=10)
    rig.zap.script = [(10, "RUNNING")] * 8 + [(100, "FINISHED")]

    rig.run_scan()

    log = rig.zap.rule_log
    add2 = log.index(("add", f"{REPLACER_RULE_PREFIX}auth-user_a-2-1"))
    remove1 = log.index(("remove", f"{REPLACER_RULE_PREFIX}auth-user_a-1-1"))
    assert add2 < remove1
    assert rig.zap.installed == {}
    logins = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert len(logins) >= 3


def test_rules_are_removed_at_the_end_of_a_normal_run() -> None:
    rig = ready()

    rig.run_scan()

    assert rig.zap.installed == {}
    assert rig.zap.rules == ["outra-regra"]
    assert rig.zap.removed_prefixes[-1] == REPLACER_RULE_PREFIX


def test_stale_harness_rules_from_older_runs_are_swept_before_installing() -> None:
    rig = ready()
    rig.zap.rules.append("hdast-old")

    rig.run_scan()

    assert "hdast-old" not in rig.zap.rules
    assert "outra-regra" in rig.zap.rules


def test_csrf_targets_get_the_header_and_the_cookie_rules_with_the_current_value() -> None:
    rig = ready(csrf=True)

    rig.run_scan()

    header = rig.zap.ever_installed[f"{REPLACER_RULE_PREFIX}csrf-header-user_a-1"]
    cookie = rig.zap.ever_installed[f"{REPLACER_RULE_PREFIX}csrf-cookie-user_a-1"]
    assert (header.match_type, header.match_string, header.replacement) == (
        "REQ_HEADER",
        "X-XSRF-TOKEN",
        CSRF_VALUE,
    )
    assert (cookie.match_type, cookie.match_string, cookie.regex, cookie.replacement) == (
        "REQ_HEADER",
        "Cookie",
        False,
        f"XSRF-TOKEN={CSRF_VALUE}",
    )
    assert rig.zap.installed == {}


def test_csrf_value_never_reaches_the_artifacts() -> None:
    rig = ready(csrf=True)

    rig.run_scan()

    written = rig.artifacts.serialized() + rig.store.serialized()
    assert CSRF_VALUE not in written
    assert TOKEN not in written
