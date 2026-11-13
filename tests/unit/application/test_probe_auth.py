"""`probe`: novo login após 401, espera de 429 e proteção CSRF."""

from typing import Any

from harness_dast.application.probe import ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.http_messages import HttpRequest
from harness_dast.domain.probe_result import ProbeResult
from tests.fakes.probe_ports import reply
from tests.fakes.rig import (
    STR,
    TOKEN,
    Rig,
    agenda_profile,
    default_handler,
    operation,
    profile_data,
)

TOKEN_2 = "tok-SEGUNDO-0987654321"  # noqa: S105 - sentinela ou nome de campo, não um segredo


def run(rig: Rig, **changes: Any) -> ProbeResult:
    return rig.probe().execute(ProbeRequest(product="agenda", **changes))


def one_get() -> ApiSpec:
    return ApiSpec(title="T", version="1", operations=(operation("ler", "get", "/api/ler"),))


def header(request: HttpRequest, name: str) -> str | None:
    return dict(request.headers).get(name)


def test_a_401_triggers_exactly_one_new_login_and_one_retry() -> None:
    logins: list[int] = []
    seen: list[str | None] = []

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            logins.append(1)
            return reply(200, {"access_token": TOKEN if len(logins) == 1 else TOKEN_2})
        seen.append(header(request, "Authorization"))
        if header(request, "Authorization") == f"Bearer {TOKEN}":
            return reply(401, {"detail": "expirou"})
        return reply(200, {})

    result = run(Rig(spec=one_get(), handler=handler))

    item = result.operations[0]
    assert item.outcome == "success"
    assert item.attempts == 2
    assert len(logins) == 2
    assert seen == [f"Bearer {TOKEN}", f"Bearer {TOKEN_2}"]


def test_a_second_401_is_reported_as_auth_error_without_a_third_attempt() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        return reply(401, {"detail": "nao"})

    rig = Rig(spec=one_get(), handler=handler)

    item = run(rig).operations[0]

    assert item.outcome == "auth_error"
    assert item.attempts == 2
    assert sum(1 for r in rig.target.requests if r.operation_id == "ler") == 2
    assert sum(1 for r in rig.target.requests if r.operation_id == "auth.login") == 2


def test_a_429_waits_for_retry_after_then_succeeds() -> None:
    state = {"n": 0}

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        state["n"] += 1
        return reply(429, {}, retry_after="2") if state["n"] == 1 else reply(200, {})

    rig = Rig(spec=one_get(), handler=handler)

    item = run(rig).operations[0]

    assert item.outcome == "success"
    assert item.attempts == 2
    assert 2.0 in rig.clock.sleeps


def test_429_gives_up_after_three_bounded_waits() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        return reply(429, {}, retry_after="9999")

    rig = Rig(spec=one_get(), handler=handler)

    item = run(rig).operations[0]

    assert item.outcome == "rate_limited"
    assert item.attempts == 4
    assert item.untrusted_target_data is not None
    assert item.untrusted_target_data.retry_after == "9999"
    waits = [s for s in rig.clock.sleeps if s >= 1]
    assert waits == [30.0, 30.0, 30.0]


def csrf_profile() -> Any:
    return agenda_profile(
        auth={**profile_data()["auth"], "csrf": {"fetch_path": "/api/csrf"}},
    )


def post_spec() -> ApiSpec:
    return ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("ler", "get", "/api/ler"),
            operation("gravar", "post", "/api/gravar", body={"nome": STR}, required=("nome",)),
            operation("trocar", "put", "/api/trocar", body={"nome": STR}, required=("nome",)),
        ),
    )


def csrf_handler(rotate_on: str | None = None) -> Any:
    tokens = {"n": 0}

    def fresh(jar: dict[str, str]) -> str:
        tokens["n"] += 1
        jar["XSRF-TOKEN"] = f"csrf-{tokens['n']}"
        return jar["XSRF-TOKEN"]

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        path = request.url.split("://", 1)[1].split("/", 1)[1]
        if path == "api/csrf":
            fresh(jar)
            return reply(200, {})
        sent = header(request, "X-XSRF-TOKEN")
        unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        if unsafe and request.operation_id != "auth.login" and sent != jar.get("XSRF-TOKEN"):
            return reply(403, {"message": "Invalid CSRF Token"})
        if request.operation_id == "auth.login":
            if sent != jar.get("XSRF-TOKEN"):
                return reply(403, {"message": "Invalid CSRF Token"})
            fresh(jar)
            return reply(200, {"access_token": TOKEN})
        if rotate_on == request.operation_id and tokens["n"] < 4:
            fresh(jar)
            return reply(403, {"message": "Invalid CSRF Token"})
        return default_handler(request, jar)

    return handler


def test_csrf_header_goes_only_on_the_listed_methods() -> None:
    rig = Rig(profile=csrf_profile(), spec=post_spec(), handler=csrf_handler())

    result = run(rig)

    assert [i.outcome for i in result.operations] == ["success"] * 3
    by_op = {r.operation_id: r for r in rig.target.requests}
    assert header(by_op["ler"], "X-XSRF-TOKEN") is None
    assert header(by_op["gravar"], "X-XSRF-TOKEN") is not None
    assert header(by_op["trocar"], "X-XSRF-TOKEN") is not None


def test_csrf_token_is_fetched_before_login_and_again_after_it() -> None:
    rig = Rig(profile=csrf_profile(), spec=post_spec(), handler=csrf_handler())

    run(rig)

    first = [r.operation_id for r in rig.target.requests][:3]
    assert first == ["auth.csrf", "auth.login", "auth.csrf"]


def test_a_csrf_rejection_refreshes_the_token_once_and_retries() -> None:
    rig = Rig(profile=csrf_profile(), spec=post_spec(), handler=csrf_handler(rotate_on="gravar"))

    result = run(rig)

    gravar = next(i for i in result.operations if i.operation_id == "gravar")
    assert gravar.outcome == "success"
    assert gravar.attempts == 2
    fetches = [r for r in rig.target.requests if r.operation_id == "auth.csrf"]
    assert len(fetches) == 3


def test_a_persistent_csrf_rejection_is_reported_as_csrf_error_after_one_refresh() -> None:
    def always_forbidden(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id in {"auth.csrf"}:
            jar["XSRF-TOKEN"] = "x"
            return reply(200, {})
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        if request.method == "POST":
            return reply(403, {"message": "Could not verify the provided CSRF token"})
        return reply(200, {})

    rig = Rig(profile=csrf_profile(), spec=post_spec(), handler=always_forbidden)

    gravar = next(i for i in run(rig).operations if i.operation_id == "gravar")

    assert gravar.outcome == "csrf_error"
    assert gravar.attempts == 2


def test_a_plain_authorization_403_is_an_auth_error_and_does_not_refresh_csrf() -> None:
    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        if request.operation_id == "auth.csrf":
            jar["XSRF-TOKEN"] = "x"
            return reply(200, {})
        if request.operation_id == "auth.login":
            return reply(200, {"access_token": TOKEN})
        if request.method == "POST":
            return reply(403, {"message": "voce nao tem permissao"})
        return reply(200, {})

    rig = Rig(profile=csrf_profile(), spec=post_spec(), handler=handler)

    gravar = next(i for i in run(rig).operations if i.operation_id == "gravar")

    assert gravar.outcome == "auth_error"
    assert gravar.attempts == 1


def test_api_key_auth_sends_the_key_header_and_never_logs_in() -> None:
    data = profile_data()
    data["auth"] = {
        "type": "api_key",
        "header_name": "X-API-Key",
        "accounts": [
            {"alias": "svc", "role": "servico", "api_key": {"secret_ref": "env:ACME_CHAVE"}}
        ],
    }
    seen: list[str | None] = []

    def handler(request: HttpRequest, jar: dict[str, str]) -> Any:
        seen.append(header(request, "X-API-Key"))
        return reply(200, {})

    rig = Rig(
        profile=agenda_profile(auth=data["auth"]),
        spec=one_get(),
        handler=handler,
        env={"ACME_CHAVE": "chave-fixa-777"},
    )

    result = run(rig)

    assert result.operations[0].outcome == "success"
    assert seen == ["chave-fixa-777"]
    assert all(r.operation_id != "auth.login" for r in rig.target.requests)
