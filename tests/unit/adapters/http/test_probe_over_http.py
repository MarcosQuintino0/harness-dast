"""`probe` de ponta a ponta sobre HTTP real: cliente `httpx`, proxy e alvo num servidor local.

O mesmo servidor faz de alvo e de proxy do ZAP (a URL absoluta chega na linha de requisição).
As duas estratégias de autenticação (login e chave de API) e o CSRF por cookie são exercidos
com o cliente de verdade; só o ZAP (API de controle) e o armazém são falsos.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qs

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.adapters.http.target_client import HttpxTargetClient, TargetClientSettings
from harness_dast.application.probe import Probe, ProbeRequest
from harness_dast.domain.api_model import ApiSpec
from harness_dast.domain.probe_result import ProbeResult
from harness_dast.domain.profile import ProductProfile
from harness_dast.observability.logging import SecretRegistry
from tests.fakes.local_server import Handler, LocalServer, Received, Reply, serve
from tests.fakes.probe_ports import (
    DictSecretProvider,
    FakeZap,
    InMemoryDocuments,
    InMemoryRunStore,
    InMemorySpecs,
)
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.rig import ENV, LOGIN, PASSWORD, STR, TOKEN, operation
from tests.fakes.runtime import FixedEntropy, ManualClock

TOKEN_2 = "tok-ROTACIONADO-5555555555"  # noqa: S105 - sentinela ou nome de campo, não um segredo


def local_profile(server: LocalServer, **auth_changes: Any) -> ProductProfile:
    data = valid_profile_data("agenda")
    data["environment"]["base_url"] = server.base_url
    data["scope"]["allow"] = [
        {
            "host": "127.0.0.1",
            "scheme": "http",
            "port": server.port,
            "paths": ["/api/**"],
            "methods": ["GET", "POST", "PUT"],
            "allow_local": True,
        }
    ]
    data["scope"]["deny_paths"] = []
    data["auth"].update(auth_changes)
    return ProductProfile.from_data(data)


def spec() -> ApiSpec:
    return ApiSpec(
        title="T",
        version="1",
        operations=(
            operation("ler", "get", "/api/ler"),
            operation("gravar", "post", "/api/gravar", body={"nome": STR}, required=("nome",)),
        ),
    )


@contextmanager
def run_probe(
    server: LocalServer, profile: ProductProfile, env: dict[str, str] | None = None
) -> Iterator[tuple[ProbeResult, InMemoryRunStore, SecretRegistry]]:
    clock = ManualClock()
    store = InMemoryRunStore()
    vault = SecretRegistry()
    client = HttpxTargetClient(
        TargetClientSettings(zap_proxy_url=server.base_url, timeout_seconds=5.0)
    )
    profiles = InMemoryProfileRepository()
    profiles.add(profile, existing_files={"./openapi.json"})
    probe = Probe(
        profiles=profiles,
        specs=InMemorySpecs(spec()),
        documents=InMemoryDocuments(),
        secrets=DictSecretProvider(ENV if env is None else env),
        vault=vault,
        client=client,
        zap=FakeZap(),
        store=store,
        clock=clock,
        sleeper=clock,
        entropy=FixedEntropy(),
        value_sources=GeneratorCatalogue,
        harness_version="0.0-test",
    )
    try:
        result: ProbeResult = probe.execute(ProbeRequest(product="agenda"))
        yield result, store, vault
    finally:
        client.close()


def cookies_of(r: Received) -> dict[str, str]:
    pairs = (item.split("=", 1) for item in r.headers.get("cookie", "").split("; ") if item)
    return {name: value for name, value in pairs}


def token_server(counter: dict[str, int]) -> Handler:
    """Alvo com login por JSON ou formulário, token Bearer e CSRF por cookie duplicado."""

    def handler(r: Received) -> Reply:
        cookies = cookies_of(r)
        if r.path == "/api/csrf":
            counter["csrf"] += 1
            return Reply(200, b"{}", [("Set-Cookie", f"XSRF-TOKEN=csrf{counter['csrf']}; Path=/")])
        if r.method != "GET" and r.headers.get("x-xsrf-token") != cookies.get("XSRF-TOKEN"):
            return Reply(403, b'{"message":"Invalid CSRF Token"}')
        if r.path == "/api/auth/login":
            counter["login"] += 1
            if r.headers.get("content-type") == "application/json":
                creds = json.loads(r.body)
            else:
                creds = {k: v[0] for k, v in parse_qs(r.body.decode()).items()}
            if creds != {"username": LOGIN, "password": PASSWORD}:
                return Reply(401, b"{}")
            token = TOKEN if counter["login"] == 1 else TOKEN_2
            return Reply(
                200,
                json.dumps({"access_token": token}).encode(),
                [("Set-Cookie", f"XSRF-TOKEN=rot{counter['login']}; Path=/")],
            )
        if r.headers.get("authorization") not in {f"Bearer {TOKEN}", f"Bearer {TOKEN_2}"}:
            return Reply(401, b"{}")
        return Reply(200, b'{"ok":true}')

    return handler


def test_login_json_with_csrf_over_real_http_and_through_the_proxy_route() -> None:
    counter = {"csrf": 0, "login": 0}
    with serve(token_server(counter)) as server:
        profile = local_profile(
            server,
            request_encoding="json",
            csrf={"fetch_path": "/api/csrf"},
        )
        with run_probe(server, profile) as (result, store, vault):
            pass

    assert [i.outcome for i in result.operations] == ["success", "success"]
    by_path = {(r.method, r.path): r for r in server.requests}
    login = by_path[("POST", "/api/auth/login")]
    assert not login.is_absolute  # login sai fora do ZAP
    assert not by_path[("GET", "/api/csrf")].is_absolute
    ler = by_path[("GET", "/api/ler")]
    gravar = by_path[("POST", "/api/gravar")]
    assert ler.is_absolute  # as operações saem pelo proxy
    assert gravar.is_absolute
    assert ler.headers["authorization"] == f"Bearer {TOKEN}"
    assert "x-xsrf-token" not in ler.headers
    assert gravar.headers["x-xsrf-token"] == "csrf2"
    assert "XSRF-TOKEN=csrf2" in gravar.headers["cookie"]
    assert counter == {"csrf": 2, "login": 1}
    assert PASSWORD not in store.serialized()
    assert vault.mask(TOKEN) == "***"


def test_login_with_form_encoding() -> None:
    counter = {"csrf": 0, "login": 0}
    with serve(token_server(counter)) as server:
        profile = local_profile(server, request_encoding="form", csrf={"fetch_path": "/api/csrf"})
        with run_probe(server, profile) as (result, _, _):
            pass

    login = next(r for r in server.requests if r.path == "/api/auth/login")
    assert login.headers["content-type"] == "application/x-www-form-urlencoded"
    assert result.operations[0].outcome == "success"


def test_a_csrf_rejection_is_recovered_with_a_fresh_token_over_real_http() -> None:
    counter = {"csrf": 0, "login": 0}
    base = token_server(counter)
    state = {"rotated": False}

    def handler(r: Received) -> Reply:
        if r.path == "/api/gravar" and not state["rotated"]:
            state["rotated"] = True
            counter["csrf"] += 1
            return Reply(
                403,
                b'{"message":"Invalid CSRF Token"}',
                [("Set-Cookie", f"XSRF-TOKEN=csrf{counter['csrf']}; Path=/")],
            )
        return base(r)

    with serve(handler) as server:
        profile = local_profile(server, request_encoding="json", csrf={"fetch_path": "/api/csrf"})
        with run_probe(server, profile) as (result, _, _):
            pass

    gravar = next(i for i in result.operations if i.operation_id == "gravar")
    assert gravar.outcome == "success"
    assert gravar.attempts == 2


def test_api_key_strategy_sends_the_fixed_header_without_any_login() -> None:
    def handler(r: Received) -> Reply:
        if r.headers.get("x-api-key") != "chave-777":
            return Reply(401, b"{}")
        return Reply(200, b"{}")

    with serve(handler) as server:
        profile = local_profile(server)
        data = profile.model_dump(mode="json")
        data["auth"] = {
            "type": "api_key",
            "header_name": "X-API-Key",
            "accounts": [{"alias": "svc", "role": "s", "api_key": {"secret_ref": "env:K"}}],
        }
        data["environment"]["verify_tls"] = True
        with run_probe(server, ProductProfile.from_data(data), {"K": "chave-777"}) as (
            result,
            _,
            _,
        ):
            pass

    assert [i.outcome for i in result.operations] == ["success", "success"]
    assert all(r.path != "/api/auth/login" for r in server.requests)


def test_token_rotation_after_a_401_uses_a_new_login_over_real_http() -> None:
    counter = {"csrf": 0, "login": 0}
    base = token_server(counter)
    first_call = {"done": False}

    def handler(r: Received) -> Reply:
        if r.path == "/api/ler" and not first_call["done"]:
            first_call["done"] = True
            return Reply(401, b"{}")
        return base(r)

    with serve(handler) as server:
        profile = local_profile(server, request_encoding="json", csrf={"fetch_path": "/api/csrf"})
        with run_probe(server, profile) as (result, _, _):
            pass

    ler = [r for r in server.requests if r.path == "/api/ler"]
    assert [r.headers["authorization"] for r in ler] == [f"Bearer {TOKEN}", f"Bearer {TOKEN_2}"]
    assert result.operations[0].outcome == "success"
    assert counter["login"] == 2
