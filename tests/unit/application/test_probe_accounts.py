"""`probe` com várias contas, orçamento de login, token vencido e códigos de erro do alvo."""

from typing import Any

import pytest

from harness_dast.application.account_session import TokenCache
from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from tests.fakes.probe_ports import Handler, reply
from tests.fakes.rig import ENV, Rig, operation, profile_data

TOKENS = {"alice": "tok-ALICE-1234567890", "bruno": "tok-BRUNO-1234567890"}
ACCOUNTS_ENV = {**ENV, "ACME_USER_B_LOGIN": "bruno", "ACME_USER_B_SENHA": "senha-do-bruno-xyz"}


def two_accounts(**auth: Any) -> dict[str, Any]:
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
    return data


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


def multi_handler(request: HttpRequest, jar: dict[str, str]) -> Any:
    if request.operation_id == "auth.login":
        who = request.body.decode() if request.body else ""
        name = "bruno" if "bruno" in who else "alice"
        return reply(200, {"access_token": TOKENS[name]})
    return reply(200, {"ok": True})


def run(rig: Rig, **changes: Any) -> ProbeResult:
    return rig.probe().execute(ProbeRequest(product="agenda", **changes))


def tokens_sent(rig: Rig, operation_id: str) -> list[str | None]:
    return [
        dict(r.headers).get("Authorization")
        for r in rig.target.requests
        if r.operation_id == operation_id
    ]


def rig_with(data: dict[str, Any], handler: Any = multi_handler) -> Rig:
    return Rig(profile=agenda_profile_from(data), spec=spec(), handler=handler, env=ACCOUNTS_ENV)


def agenda_profile_from(data: dict[str, Any]) -> ProductProfile:
    return ProductProfile.from_data(data)


def test_each_operation_goes_out_with_the_account_the_map_chooses() -> None:
    data = two_accounts(
        account_map=[{"account": "user_b", "operations": ["gravar"]}],
    )
    rig = rig_with(data)

    result = run(rig)

    by_op = {item.operation_id: item.account for item in result.operations}
    assert by_op["ler"] == "user_a"
    assert by_op["gravar"] == "user_b"
    assert tokens_sent(rig, "gravar") == [f"Bearer {TOKENS['bruno']}"]
    assert tokens_sent(rig, "ler") == [f"Bearer {TOKENS['alice']}"]


def test_a_path_pattern_with_method_picks_the_account() -> None:
    data = two_accounts(
        default_account="user_b",
        account_map=[{"account": "user_a", "path": "/api/receitas/**", "methods": ["GET"]}],
    )
    rig = rig_with(data)

    by_op = {item.operation_id: item.account for item in run(rig).operations}

    assert by_op == {"ler": "user_b", "gravar": "user_b", "receita": "user_a"}


def test_every_account_logs_in_exactly_once_per_run() -> None:
    data = two_accounts(account_map=[{"account": "user_b", "operations": ["gravar", "receita"]}])
    rig = rig_with(data)

    run(rig)

    logins = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert sorted(r.account or "" for r in logins) == ["user_a", "user_b"]


def test_the_account_flag_pins_every_operation_to_one_account() -> None:
    data = two_accounts(account_map=[{"account": "user_b", "operations": ["gravar"]}])
    rig = rig_with(data)

    result = run(rig, account="user_a")

    assert {item.account for item in result.operations if item.outcome == "success"} == {"user_a"}
    assert not [r for r in rig.target.requests if r.account == "user_b"]


def test_the_manifest_lists_only_the_accounts_the_plan_uses() -> None:
    rig = rig_with(two_accounts(account_map=[{"account": "user_b", "operations": ["gravar"]}]))

    result = run(rig)

    manifest = rig.store.manifests[result.run_id][-1]
    assert manifest.accounts == ("user_a", "user_b")


def test_an_account_map_naming_an_unknown_operation_is_a_config_error() -> None:
    rig = rig_with(two_accounts(account_map=[{"account": "user_b", "operations": ["inexistente"]}]))

    with pytest.raises(ConfigError, match="inexistente"):
        run(rig)

    assert rig.target.requests == []


def test_the_dry_run_sends_nothing_and_does_not_log_in() -> None:
    rig = rig_with(two_accounts(account_map=[{"account": "user_b", "operations": ["gravar"]}]))

    run(rig, dry_run=True)

    assert rig.target.requests == []


# -------------------------------------------------------------- token vencido


def expiring_handler(code: str | None) -> Handler:
    state = {"logins": 0}

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            state["logins"] += 1
            return reply(200, {"access_token": f"tok-N{state['logins']}-1234567890"})
        if dict(request.headers).get("Authorization") == "Bearer tok-N1-1234567890":
            return reply(401, {"code": code} if code else {"detail": "x"})
        return reply(200, {"ok": True})

    return handler


def test_a_401_with_the_declared_expiry_code_logs_in_again_once() -> None:
    data = two_accounts(token_expired={"field": "code", "value": "TOKEN_EXPIRADO"})
    rig = rig_with(data, expiring_handler("TOKEN_EXPIRADO"))

    item = run(rig, only=("ler",)).operations[0]

    assert item.outcome == "success"
    assert item.attempts == 2


def test_a_401_with_another_code_is_not_an_expiry_when_the_signal_is_declared() -> None:
    data = two_accounts(token_expired={"field": "code", "value": "TOKEN_EXPIRADO"})
    rig = rig_with(data, expiring_handler("TOKEN_INVALIDO"))

    item = run(rig, only=("ler",)).operations[0]

    assert item.outcome == "auth_error"
    assert item.attempts == 1
    assert len([r for r in rig.target.requests if r.operation_id == "auth.login"]) == 1


def test_without_a_declared_signal_any_401_logs_in_again() -> None:
    rig = rig_with(two_accounts(), expiring_handler(None))

    item = run(rig, only=("ler",)).operations[0]

    assert item.outcome == "success"
    assert item.attempts == 2


# ------------------------------------------------------------ orçamento de login


def test_logins_never_exceed_the_declared_rate_in_any_sixty_second_window() -> None:
    stamps: list[float] = []
    holder: dict[str, Rig] = {}

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            stamps.append(holder["rig"].clock.now().timestamp())
            return reply(200, {"access_token": TOKENS["alice"]})
        return reply(200, {"ok": True})

    data = profile_data()
    for index in range(2, 5):
        data["auth"]["accounts"].append(
            {
                "alias": f"user_{index}",
                "role": "outro",
                "username": {"secret_ref": "env:ACME_USER_A_LOGIN"},
                "password": {"secret_ref": "env:ACME_USER_A_SENHA"},
            }
        )
    data["auth"]["login_limit"] = {"max_per_minute": 2}
    data["auth"]["account_map"] = [
        {"account": "user_2", "operations": ["gravar"]},
        {"account": "user_3", "operations": ["receita"]},
    ]
    rig = Rig(profile=agenda_profile_from(data), spec=spec(), handler=handler)
    holder["rig"] = rig

    result = run(rig)

    assert result.status == "completed"
    assert len(stamps) == 3
    for stamp in stamps:
        assert len([other for other in stamps if 0 <= other - stamp < 60]) <= 2
    assert max(stamps) - min(stamps) >= 60


def test_a_429_on_login_waits_for_retry_after_and_counts_against_the_budget() -> None:
    attempts = {"n": 0}

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return reply(429, {"code": "LIMITE_EXCEDIDO"}, retry_after="7")
            return reply(200, {"access_token": TOKENS["alice"]})
        return reply(200, {"ok": True})

    data = two_accounts()
    data["auth"]["login_limit"] = {"max_per_minute": 5}
    rig = rig_with(data, handler)

    result = run(rig, only=("ler",))

    assert result.operations[0].outcome == "success"
    assert 7.0 in rig.clock.sleeps
    assert attempts["n"] == 2


def test_preflight_and_probe_in_one_process_log_in_once_per_account() -> None:
    rig = rig_with(two_accounts(account_map=[{"account": "user_b", "operations": ["gravar"]}]))
    cache = TokenCache()
    preflight = rig.preflight(cache)
    probe = rig.probe(cache)

    report = preflight.execute("agenda")
    run_result = probe.execute(ProbeRequest(product="agenda"))

    assert report.ready
    assert run_result.summary.successes >= 1
    logins = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert sorted(r.account or "" for r in logins) == ["user_a", "user_b"]


def test_preflight_alone_logs_in_once_per_account() -> None:
    rig = rig_with(two_accounts())

    rig.preflight().execute("agenda")

    logins = [r for r in rig.target.requests if r.operation_id == "auth.login"]
    assert sorted(r.account or "" for r in logins) == ["user_a", "user_b"]


# --------------------------------------------------------- códigos de erro


def coded_handler(status: int, body: Any) -> Handler:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKENS["alice"]})
        return reply(status, body)

    return handler


CODES = {
    "field": "code",
    "outcomes": {
        "validation_error": ["VALIDACAO"],
        "conflict": ["CONFLITO", "TRANSICAO_INVALIDA"],
        "csrf_error": ["XSRF_INVALIDO"],
    },
}


def coded_data() -> dict[str, Any]:
    data = two_accounts()
    data["probe"] = {"health_path": "/api/saude", "error_codes": CODES}
    return data


def test_a_declared_code_overrides_the_status_heuristic() -> None:
    rig = rig_with(coded_data(), coded_handler(409, {"code": "TRANSICAO_INVALIDA"}))

    assert run(rig, only=("ler",)).operations[0].outcome == "conflict"


def test_a_declared_validation_code_keeps_the_per_field_detail() -> None:
    body = {
        "code": "VALIDACAO",
        "message": "dados invalidos",
        "errors": [{"field": "cpf", "rule": "CPF", "message": "cpf invalido"}],
    }
    rig = rig_with(coded_data(), coded_handler(400, body))

    item = run(rig, only=("ler",)).operations[0]

    assert item.outcome == "validation_error"
    assert item.untrusted_target_data is not None
    assert '"field": "cpf"' in item.untrusted_target_data.excerpt
    assert '"rule": "CPF"' in item.untrusted_target_data.excerpt


def test_an_unknown_code_falls_back_to_the_status_heuristic() -> None:
    rig = rig_with(coded_data(), coded_handler(409, {"code": "OUTRO"}))

    assert run(rig, only=("ler",)).operations[0].outcome == "conflict"


def test_a_declared_csrf_code_triggers_one_token_refresh() -> None:
    data = coded_data()
    data["auth"]["csrf"] = {"fetch_path": "/api/csrf"}
    fetches = {"n": 0}

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKENS["alice"]})
        if request.operation_id == "auth.csrf":
            fetches["n"] += 1
            jar["XSRF-TOKEN"] = f"csrf-{fetches['n']}-abcdefgh"
            return reply(200, {"token": "x"})
        if (
            request.method == "POST"
            and dict(request.headers).get("X-XSRF-TOKEN") != "csrf-3-abcdefgh"
        ):
            return reply(403, {"code": "XSRF_INVALIDO", "message": "token ausente ou invalido"})
        return reply(200, {"ok": True})

    rig = rig_with(data, handler)

    item = next(i for i in run(rig).operations if i.operation_id == "gravar")

    assert item.outcome == "success"
    assert item.attempts == 2
