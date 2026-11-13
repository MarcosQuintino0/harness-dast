"""Cabeçalhos de roteamento: só o cliente HTTP os define; nem o OpenAPI nem um chamador."""

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.http_messages import HttpRequest, approve
from harness_dast.domain.routing_headers import is_routing_header
from harness_dast.domain.scope import Scope, ScopeGuard, ScopeRule

GUARD = ScopeGuard(
    Scope(allow=(ScopeRule(host="api.permitido.com", paths=("/**",), methods=("GET",)),))
)


@pytest.mark.parametrize(
    "name",
    [
        "Host",
        " host ",
        "CONTENT-LENGTH",
        "Transfer-Encoding",
        "Connection",
        "Upgrade",
        "TE",
        "Expect",
        "Trailer",
        "Keep-Alive",
        "Forwarded",
        "Via",
        "Proxy-Authorization",
        "proxy-connection",
        "X-Forwarded-Host",
        "x-forwarded-for",
    ],
)
def test_is_routing_header_recognises_routing_and_framing_headers(name: str) -> None:
    assert is_routing_header(name) is True


@pytest.mark.parametrize(
    "name", ["Authorization", "X-Request-Id", "Accept", "Content-Type", "Cookie", "X-Api-Key"]
)
def test_is_routing_header_lets_ordinary_headers_through(name: str) -> None:
    assert is_routing_header(name) is False


def test_approve_refuses_a_request_that_carries_a_routing_header() -> None:
    request = HttpRequest(
        method="GET",
        url="https://api.permitido.com/x",
        headers=(("Host", "outro-host.interno.example"),),
        operation_id="op",
    )

    with pytest.raises(ScopeViolation, match="roteamento"):
        approve(GUARD, request)


def test_approve_accepts_ordinary_headers() -> None:
    request = HttpRequest(
        method="GET",
        url="https://api.permitido.com/x",
        headers=(("X-Request-Id", "1"),),
        operation_id="op",
    )

    assert approve(GUARD, request).request == request
