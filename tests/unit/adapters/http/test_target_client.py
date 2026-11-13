"""Cliente HTTP do alvo contra um servidor local real."""

import shutil
import subprocess
from pathlib import Path

import pytest

from harness_dast.adapters.http.target_client import HttpxTargetClient, TargetClientSettings
from harness_dast.domain.errors import ExternalToolError, TargetTimeout, TargetUnreachable
from harness_dast.domain.http_messages import ApprovedRequest, HttpRequest, approve
from harness_dast.domain.scope import Scope, ScopeGuard, ScopeRule
from tests.fakes.local_server import Received, Reply, free_port, serve

ALLOW_ALL = ScopeGuard(
    Scope(
        allow=(
            ScopeRule(
                host="127.0.0.1",
                scheme="http",
                port=None,
                paths=("/**",),
                methods=("GET", "POST", "PUT", "DELETE"),
                allow_local=True,
            ),
        )
    )
)


def approved(
    url: str,
    *,
    method: str = "GET",
    route: str = "auth",
    account: str | None = "user_a",
    headers: tuple[tuple[str, str], ...] = (),
    body: bytes | None = None,
) -> ApprovedRequest:
    """Requisição aprovada pelo guarda; o escopo de teste libera qualquer porta local via `port`."""
    request = HttpRequest(
        method=method,
        url=url,
        headers=headers,
        body=body,
        operation_id="op",
        account=account,
        route=route,  # type: ignore[arg-type]
    )
    return _approve_any_port(request)


def _approve_any_port(request: HttpRequest) -> ApprovedRequest:
    port = int(request.url.split("://", 1)[1].split("/", 1)[0].split(":")[1])
    rule = ScopeRule(
        host="127.0.0.1",
        scheme="http",
        port=port,
        paths=("/**",),
        methods=("GET", "POST", "PUT", "DELETE"),
        allow_local=True,
    )
    return approve(ScopeGuard(Scope(allow=(rule,))), request)


def make_client(proxy: str = "http://127.0.0.1:9", **changes: object) -> HttpxTargetClient:
    settings = TargetClientSettings(zap_proxy_url=proxy, timeout_seconds=2.0)
    for name, value in changes.items():
        settings = settings.__class__(**{**settings.__dict__, name: value})
    return HttpxTargetClient(settings)


def test_direct_route_sends_origin_form_and_returns_the_reduced_response() -> None:
    def handler(r: Received) -> Reply:
        return Reply(
            201,
            b'{"ok":true}',
            [("Content-Type", "application/json"), ("Retry-After", "7"), ("X-Segredo", "nao")],
        )

    with serve(handler) as server:
        client = make_client()
        response = client.send(
            approved(
                f"{server.base_url}/api/x?a=1",
                method="POST",
                headers=(("X-Teste", "1"),),
                body=b'{"a":1}',
            )
        )

    received = server.requests[0]
    assert (received.method, received.target, received.is_absolute) == ("POST", "/api/x?a=1", False)
    assert received.body == b'{"a":1}'
    assert received.headers["x-teste"] == "1"
    assert received.headers["user-agent"] == "harness-dast"
    assert (response.status, response.content_type, response.retry_after) == (
        201,
        "application/json",
        "7",
    )
    assert response.body == b'{"ok":true}'
    assert response.body_truncated is False
    assert response.location is None
    assert response.elapsed_ms >= 0


def test_zap_route_goes_through_the_proxy_with_an_absolute_url() -> None:
    with serve(lambda r: Reply(200, b"via proxy")) as proxy:
        client = make_client(proxy=proxy.base_url)
        response = client.send(
            approved("http://127.0.0.1:65000/api/y", route="zap")  # destino que ninguém atende
        )

    assert response.body == b"via proxy"
    assert proxy.requests[0].target == "http://127.0.0.1:65000/api/y"
    assert proxy.requests[0].is_absolute


def test_auth_route_uses_its_own_proxy_when_configured_and_never_the_zap_one() -> None:
    with (
        serve(lambda r: Reply(200, b"auth proxy")) as auth_proxy,
        serve(lambda r: Reply(200, b"zap")) as zap_proxy,
    ):
        client = make_client(proxy=zap_proxy.base_url, auth_proxy_url=auth_proxy.base_url)
        client.send(approved("http://127.0.0.1:65000/login", route="auth"))

    assert auth_proxy.requests
    assert not zap_proxy.requests


def test_proxy_environment_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{free_port()}")
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{free_port()}")
    with serve(lambda r: Reply(200, b"direto")) as server:
        response = make_client().send(approved(f"{server.base_url}/x"))

    assert response.body == b"direto"
    assert not server.requests[0].is_absolute


def test_redirects_are_returned_and_never_followed() -> None:
    with serve(lambda r: Reply(302, b"", [("Location", "http://127.0.0.1:1/elsewhere")])) as server:
        response = make_client().send(approved(f"{server.base_url}/x"))

    assert response.status == 302
    assert response.location == "http://127.0.0.1:1/elsewhere"
    assert len(server.requests) == 1


def test_a_slow_target_raises_target_timeout() -> None:
    with serve(lambda r: Reply(200, b"", delay=1.5)) as server:
        client = make_client(timeout_seconds=0.3)
        with pytest.raises(TargetTimeout):
            client.send(approved(f"{server.base_url}/x"))


def test_connection_refused_is_target_unreachable_on_the_direct_route() -> None:
    with pytest.raises(TargetUnreachable) as info:
        # No Windows, a recusa de conexão local só é reportada após ~2 s.
        make_client(timeout_seconds=10.0).send(approved(f"http://127.0.0.1:{free_port()}/x"))

    assert "127.0.0.1" not in info.value.message


def test_a_dead_zap_proxy_is_an_external_tool_error_on_the_zap_route() -> None:
    client = make_client(proxy=f"http://127.0.0.1:{free_port()}", timeout_seconds=10.0)

    with pytest.raises(ExternalToolError) as info:
        client.send(approved("http://127.0.0.1:65000/x", route="zap"))

    assert "ZAP" in info.value.message


def test_the_response_body_is_read_only_up_to_the_cap() -> None:
    with serve(lambda r: Reply(200, b"x" * 100_000)) as server:
        response = make_client(max_body_bytes=1000).send(approved(f"{server.base_url}/x"))

    assert len(response.body) == 1000
    assert response.body_truncated is True


def test_a_body_exactly_at_the_cap_is_not_marked_truncated() -> None:
    with serve(lambda r: Reply(200, b"x" * 1000)) as server:
        response = make_client(max_body_bytes=1000).send(approved(f"{server.base_url}/x"))

    assert len(response.body) == 1000
    assert response.body_truncated is False


def test_cookies_are_kept_per_account_and_never_shared() -> None:
    def handler(r: Received) -> Reply:
        if r.path == "/set":
            return Reply(200, b"", [("Set-Cookie", "XSRF-TOKEN=abc123; Path=/; HttpOnly")])
        return Reply(200, b"")

    with serve(handler) as server:
        client = make_client()
        client.send(approved(f"{server.base_url}/set", account="user_a"))
        client.send(approved(f"{server.base_url}/a", account="user_a"))
        client.send(approved(f"{server.base_url}/b", account="user_b"))
        client.send(approved(f"{server.base_url}/anon", account=None))

    by_path = {r.path: r for r in server.requests}
    assert by_path["/a"].headers["cookie"] == "XSRF-TOKEN=abc123"
    assert "cookie" not in by_path["/b"].headers
    assert "cookie" not in by_path["/anon"].headers
    assert client.cookie_value("user_a", "XSRF-TOKEN") == "abc123"
    assert client.cookie_value("user_b", "XSRF-TOKEN") is None
    assert client.cookie_value("user_a", "outro") is None


def test_cookie_is_replaced_and_removed_as_the_server_says() -> None:
    def handler(r: Received) -> Reply:
        if r.path == "/novo":
            return Reply(200, b"", [("Set-Cookie", "T=2")])
        if r.path == "/apaga":
            return Reply(200, b"", [("Set-Cookie", "T=; Max-Age=0")])
        return Reply(200, b"", [("Set-Cookie", "T=1")])

    with serve(handler) as server:
        client = make_client()
        client.send(approved(f"{server.base_url}/a"))
        assert client.cookie_value("user_a", "T") == "1"
        client.send(approved(f"{server.base_url}/novo"))
        assert client.cookie_value("user_a", "T") == "2"
        client.send(approved(f"{server.base_url}/apaga"))
        assert client.cookie_value("user_a", "T") is None


def test_explicit_cookies_of_the_request_are_sent_together_with_the_jar() -> None:
    def handler(r: Received) -> Reply:
        return Reply(200, b"", [("Set-Cookie", "J=1")])

    with serve(handler) as server:
        client = make_client()
        client.send(approved(f"{server.base_url}/a"))
        client.send(approved(f"{server.base_url}/b", headers=(("Cookie", "p=9"),)))

    assert server.requests[1].headers["cookie"] == "J=1; p=9"


def test_malformed_set_cookie_is_ignored() -> None:
    with serve(lambda r: Reply(200, b"", [("Set-Cookie", "isto nao e cookie;;;=")])) as server:
        client = make_client()
        client.send(approved(f"{server.base_url}/a"))

    assert client.cookie_value("user_a", "isto") is None


def test_close_is_idempotent() -> None:
    client = make_client()

    client.close()
    client.close()


@pytest.fixture
def certificate(tmp_path: Path) -> tuple[str, str]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl indisponível para gerar o certificado de teste")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(  # noqa: S603 - comando fixo de teste
        [  # noqa: S607 - o openssl vem do PATH do desenvolvedor
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return str(cert), str(key)


def https_request(server_url: str) -> ApprovedRequest:
    request = HttpRequest(method="GET", url=f"{server_url}/x", operation_id="op", route="auth")
    port = int(server_url.rsplit(":", 1)[1])
    rule = ScopeRule(
        host="127.0.0.1",
        scheme="https",
        port=port,
        paths=("/**",),
        methods=("GET",),
        allow_local=True,
    )
    return approve(ScopeGuard(Scope(allow=(rule,))), request)


def test_tls_is_verified_by_default_and_can_be_relaxed_only_by_setting(
    certificate: tuple[str, str],
) -> None:
    with serve(lambda r: Reply(200, b"seguro"), tls=certificate) as server:
        strict = make_client()
        with pytest.raises(TargetUnreachable):
            strict.send(https_request(server.base_url))
        relaxed = make_client(verify_tls=False)
        assert relaxed.send(https_request(server.base_url)).body == b"seguro"
        pinned = make_client(zap_ca_file=Path(certificate[0]), proxy=server.base_url)
        assert pinned._zap is not pinned._auth
