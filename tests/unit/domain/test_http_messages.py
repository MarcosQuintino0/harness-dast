"""A invariante central: só uma requisição aprovada pelo `ScopeGuard` pode ser enviada."""

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.http_messages import ApprovedRequest, HttpRequest, approve
from harness_dast.domain.scope import Scope, ScopeGuard, ScopeRule

HOST = "api.permitido.com"


def guard() -> ScopeGuard:
    rule = ScopeRule(host=HOST, paths=("/api/**",), methods=("GET", "POST"))
    return ScopeGuard(Scope(allow=(rule,), deny_paths=("/api/admin/**",)))


def request(url: str, method: str = "GET") -> HttpRequest:
    return HttpRequest(method=method, url=url, operation_id="op")


def test_approve_returns_the_same_request_when_it_is_inside_the_scope() -> None:
    original = request(f"https://{HOST}/api/x?a=1")

    approved = approve(guard(), original)

    assert isinstance(approved, ApprovedRequest)
    assert approved.request == original


@pytest.mark.parametrize(
    ("url", "method"),
    [
        (f"https://{HOST}/api/admin/x", "GET"),
        ("https://outro.example.org/api/x", "GET"),
        (f"https://{HOST}/api/x", "DELETE"),
        (f"http://{HOST}/api/x", "GET"),
        (f"https://{HOST}/fora", "GET"),
    ],
)
def test_approve_refuses_requests_outside_the_scope(url: str, method: str) -> None:
    with pytest.raises(ScopeViolation):
        approve(guard(), request(url, method))


def test_an_approved_request_cannot_be_built_directly() -> None:
    with pytest.raises(TypeError):
        ApprovedRequest(request(f"https://{HOST}/api/x"), _mint=object())


def test_an_approved_request_cannot_be_built_without_the_private_mark() -> None:
    with pytest.raises(TypeError):
        ApprovedRequest(request(f"https://{HOST}/api/x"))  # type: ignore[call-arg]


def test_an_approved_request_cannot_be_subclassed() -> None:
    with pytest.raises(TypeError):

        class Forged(ApprovedRequest):  # pragma: no cover - a definição já falha
            pass


def test_an_approved_request_is_immutable() -> None:
    approved = approve(guard(), request(f"https://{HOST}/api/x"))

    with pytest.raises(AttributeError):
        approved.request = request("https://outro.example.org/")  # type: ignore[misc]
    with pytest.raises(AttributeError):
        approved.novo = 1


def test_the_scope_violation_message_does_not_repeat_the_path() -> None:
    with pytest.raises(ScopeViolation) as info:
        approve(guard(), request(f"https://{HOST}/api/admin/segredo-token-123"))

    assert "segredo-token-123" not in info.value.message
