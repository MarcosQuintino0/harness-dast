"""`scan` com várias contas: cada varredura usa o token da conta que enviou a requisição."""

from typing import Any

import pytest

from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import reply
from tests.fakes.rig import ENV, operation, profile_data
from tests.fakes.scan_rig import ScanRig

ALICE = "tok-ALICE-1234567890"
BRUNO = "tok-BRUNO-1234567890"
TOKENS = {"alice": ALICE, "bruno": BRUNO}
ACCOUNTS_ENV = {**ENV, "ACME_USER_B_LOGIN": "bruno", "ACME_USER_B_SENHA": "senha-do-bruno-xyz"}


def profile(**auth: Any) -> ProductProfile:
    data = profile_data()
    data["auth"]["accounts"].append(
        {
            "alias": "user_b",
            "role": "outro",
            "username": {"secret_ref": "env:ACME_USER_B_LOGIN"},
            "password": {"secret_ref": "env:ACME_USER_B_SENHA"},
        }
    )
    data["auth"].update(auth)
    return ProductProfile.from_data(data)


def spec() -> ApiSpec:
    return ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("ler", "get", "/api/ler"),
            operation("gravar", "post", "/api/gravar", body={}),
            operation("receita", "get", "/api/receitas/{id}"),
        ),
    )


def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
    if request.operation_id == "auth.login":
        who = request.body.decode() if request.body else ""
        return reply(200, {"access_token": TOKENS["bruno" if "bruno" in who else "alice"]})
    return reply(200, {"ok": True})


def ready(**auth: Any) -> ScanRig:
    rig = ScanRig(profile=profile(**auth), spec=spec(), handler=handler, env=ACCOUNTS_ENV)
    rig.run_probe()
    return rig


def replacements(rig: ScanRig) -> list[str]:
    return [rule.replacement for rule in rig.zap.ever_installed.values()]


def test_each_scan_uses_the_token_of_the_account_that_sent_the_request_in_the_probe() -> None:
    rig = ready(account_map=[{"account": "user_b", "operations": ["gravar"]}])

    result = rig.run_scan()

    assert result.status == "completed"
    assert sorted(replacements(rig)) == sorted([f"Bearer {ALICE}", f"Bearer {BRUNO}"])
    by_scan = [
        (request.method, rules)
        for request, rules in zip(rig.zap.started, rig.zap.rules_at_start, strict=True)
    ]
    assert [method for method, _ in by_scan] == ["GET", "GET", "POST"]
    assert all(len(rules) == 1 for _, rules in by_scan)


def test_scans_are_grouped_by_account_so_the_token_changes_only_once() -> None:
    rig = ready(account_map=[{"account": "user_b", "operations": ["ler"]}])

    rig.run_scan()

    adds = [name for event, name in rig.zap.rule_log if event == "add"]
    assert len(adds) == 2
    first_removal = next(i for i, (event, _) in enumerate(rig.zap.rule_log) if event == "remove")
    assert rig.zap.rule_log[first_removal - 1][0] == "add"
    assert first_removal == 1


def test_only_one_accounts_rules_are_installed_at_any_time() -> None:
    rig = ready(account_map=[{"account": "user_b", "operations": ["gravar", "receita"]}])

    rig.run_scan()

    live = 0
    peak = 0
    for event, _ in rig.zap.rule_log:
        live += 1 if event == "add" else -1
        peak = max(peak, live)
    assert peak == 1
    assert rig.zap.installed == {}


def test_every_account_logs_in_once_for_the_scan_without_a_refresh() -> None:
    rig = ready(account_map=[{"account": "user_b", "operations": ["gravar"]}])
    logins_before = len([r for r in rig.target.requests if r.operation_id == "auth.login"])

    rig.run_scan()

    logins = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert len(logins) - logins_before == 2


def test_the_account_flag_pins_every_scan_to_one_account() -> None:
    rig = ready(account_map=[{"account": "user_b", "operations": ["gravar"]}])

    rig.run_scan(account="user_a")

    assert replacements(rig) == [f"Bearer {ALICE}"]
    assert len(rig.zap.started) == 3


def test_an_unknown_pinned_account_is_a_config_error() -> None:
    rig = ready()

    with pytest.raises(ConfigError, match="conta"):
        rig.run_scan(account="nao_existe")
