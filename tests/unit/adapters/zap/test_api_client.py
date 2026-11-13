"""Cliente da API do ZAP contra um ZAP falso que repete as formas de resposta do spike do M0."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from harness_dast.adapters.zap.api_client import ZapApiClient
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.local_server import Received, Reply, free_port, serve

API_KEY = "chave-zap-segredo-123"


def ok(payload: object, status: int = 200) -> Reply:
    return Reply(status, json.dumps(payload).encode(), [("Content-Type", "application/json")])


def query(received: Received) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(received.target).query).items()}


class FakeZapServer:
    """Respostas copiadas do spike: ZAP 2.17.0."""

    def __init__(self) -> None:
        self.rules = [
            {"description": "hdast-auth"},
            {"description": "hdast-x"},
            {"description": "mine"},
        ]
        self.addon_missing = False

    def __call__(self, r: Received) -> Reply:
        if r.headers.get("x-zap-api-key") != API_KEY:
            return ok({"code": "bad_api_key", "message": "Bad API key"}, 400)
        route = r.path
        if route == "/JSON/core/view/version/":
            return ok({"version": "2.17.0"})
        if route == "/JSON/core/action/newSession/":
            return ok({"Result": "OK"})
        if route == "/JSON/context/action/newContext/":
            return ok({"contextId": "3"})
        if route in {
            "/JSON/context/action/includeInContext/",
            "/JSON/context/action/excludeFromContext/",
        }:
            return ok({"Result": "OK"})
        if route == "/JSON/replacer/view/rules/":
            if self.addon_missing:
                return ok({"code": "no_implementor", "message": "No Implementor"}, 400)
            return ok({"rules": self.rules})
        if route == "/JSON/replacer/action/removeRule/":
            name = query(r)["description"]
            self.rules = [x for x in self.rules if x["description"] != name]
            return ok({"Result": "OK"})
        return ok({"code": "bad_action", "message": "Bad Action"}, 400)


def client_for(server_url: str, key: str | None = API_KEY) -> ZapApiClient:
    return ZapApiClient(server_url, key, timeout_seconds=2.0)


def test_version_is_read_and_the_key_travels_in_a_header_never_in_the_url() -> None:
    with serve(FakeZapServer()) as server:
        assert client_for(server.base_url).version() == "2.17.0"

    request = server.requests[0]
    assert request.headers["x-zap-api-key"] == API_KEY
    assert API_KEY not in request.target
    assert request.target == "/JSON/core/view/version/"


def test_a_session_is_started_with_a_name() -> None:
    with serve(FakeZapServer()) as server:
        client_for(server.base_url).start_session("hdast-run-1")

    assert query(server.requests[0]) == {"name": "hdast-run-1", "overwrite": "true"}


def test_context_is_created_and_limited_to_the_given_expressions() -> None:
    with serve(FakeZapServer()) as server:
        context_id = client_for(server.base_url).create_context(
            "hdast-run-1", ("^http://a/.*$", "^http://b/.*$"), ("^http://a/admin.*$",)
        )

    assert context_id == 3
    calls = [(r.path.split("/")[-2], query(r)) for r in server.requests]
    assert calls == [
        ("newContext", {"contextName": "hdast-run-1"}),
        ("includeInContext", {"contextName": "hdast-run-1", "regex": "^http://a/.*$"}),
        ("includeInContext", {"contextName": "hdast-run-1", "regex": "^http://b/.*$"}),
        ("excludeFromContext", {"contextName": "hdast-run-1", "regex": "^http://a/admin.*$"}),
    ]


def test_only_rules_with_the_harness_prefix_are_removed() -> None:
    zap = FakeZapServer()
    with serve(zap) as server:
        removed = client_for(server.base_url).remove_stale_rules("hdast-")

    assert removed == 2
    assert zap.rules == [{"description": "mine"}]


def test_a_missing_replacer_addon_means_there_is_nothing_to_remove() -> None:
    zap = FakeZapServer()
    zap.addon_missing = True
    with serve(zap) as server:
        assert client_for(server.base_url).remove_stale_rules("hdast-") == 0


def test_a_wrong_key_is_an_external_tool_error_with_a_hint_and_without_the_key() -> None:
    with serve(FakeZapServer()) as server:
        client = client_for(server.base_url, key="outra-chave-qualquer")
        with pytest.raises(ExternalToolError) as info:
            client.version()

    assert "bad_api_key" in info.value.message
    assert "HDAST_ZAP_API_KEY" in (info.value.hint or "")
    assert "outra-chave-qualquer" not in info.value.message + (info.value.hint or "")


@pytest.mark.parametrize(
    "reply",
    [
        Reply(200, b"<html>nao sou o zap</html>"),
        Reply(200, b"[1,2]"),
        Reply(500, b'{"x":1}'),
        Reply(200, b'{"version": 3}'),
        Reply(200, b"{}"),
    ],
)
def test_unexpected_answers_are_external_tool_errors(reply: Reply) -> None:
    with serve(lambda r: reply) as server, pytest.raises(ExternalToolError) as info:
        client_for(server.base_url).version()

    assert info.value.hint


def test_an_action_without_result_ok_is_rejected() -> None:
    with serve(lambda r: ok({"Result": "FALHOU"})) as server, pytest.raises(ExternalToolError):
        client_for(server.base_url).start_session("x")


def test_context_without_an_id_is_rejected() -> None:
    with serve(lambda r: ok({"contextId": "abc"})) as server, pytest.raises(ExternalToolError):
        client_for(server.base_url).create_context("x", (), ())


def test_rules_listing_with_a_bad_shape_is_rejected() -> None:
    with serve(lambda r: ok({"rules": "nope"})) as server, pytest.raises(ExternalToolError):
        client_for(server.base_url).remove_stale_rules("hdast-")


def test_error_codes_with_odd_characters_are_not_echoed() -> None:
    with (
        serve(lambda r: ok({"code": "<script>alert(1)</script>"}, 400)) as server,
        pytest.raises(ExternalToolError) as info,
    ):
        client_for(server.base_url).version()

    assert "<script>" not in info.value.message


def test_a_slow_zap_is_a_timeout_error() -> None:
    with serve(lambda r: Reply(200, b"{}", delay=1.5)) as server:
        client = ZapApiClient(server.base_url, API_KEY, timeout_seconds=0.3)
        with pytest.raises(ExternalToolError) as info:
            client.version()

    assert "tempo limite" in info.value.message


def test_an_unreachable_zap_is_an_external_tool_error() -> None:
    client = ZapApiClient(f"http://127.0.0.1:{free_port()}", None, timeout_seconds=10.0)

    with pytest.raises(ExternalToolError) as info:
        client.version()

    assert "HDAST_ZAP_BASE_URL" in (info.value.hint or "")


def test_an_oversized_response_is_refused() -> None:
    with (
        serve(lambda r: Reply(200, b"x" * (2 * 1024 * 1024))) as server,
        pytest.raises(ExternalToolError),
    ):
        client_for(server.base_url).version()


def test_no_key_header_is_sent_when_the_zap_has_no_key() -> None:
    with serve(lambda r: ok({"version": "2.17.0"})) as server:
        ZapApiClient(server.base_url, None).version()

    assert "x-zap-api-key" not in server.requests[0].headers
