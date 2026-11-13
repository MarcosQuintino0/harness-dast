"""Testes independentes (QA) da normalização de URL e de host."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import contextlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.host import parse_host
from harness_dast.domain.urlnorm import (
    KNOWN_METHODS,
    normalize_request,
    resolve_location,
)

_URL_CHARS = st.text(
    alphabet=st.sampled_from(list("abcxyz019.-:/@?#%[]\\;~ \t")) | st.characters(), max_size=40
)


@settings(max_examples=500, deadline=None)
@given(host=st.sampled_from(["a.com", "B.Example.COM.", "127.0.0.1", "[::1]"]), tail=_URL_CHARS)
def test_normalize_request_is_idempotent_when_url_is_accepted(host: str, tail: str) -> None:
    url = f"https://{host}/{tail}"
    try:
        first = normalize_request("GET", url)
    except ScopeViolation:
        return
    second = normalize_request("GET", first.url)

    assert second == first
    assert second.url == first.url


@settings(max_examples=500, deadline=None)
@given(text=st.text(max_size=60))
def test_normalize_request_raises_only_scope_violation_when_input_is_any_text(text: str) -> None:
    with contextlib.suppress(ScopeViolation):
        normalize_request("GET", text)


@settings(max_examples=500, deadline=None)
@given(text=st.text(max_size=60))
def test_parse_host_raises_only_scope_violation_when_input_is_any_text(text: str) -> None:
    with contextlib.suppress(ScopeViolation):
        parse_host(text)


@settings(max_examples=300, deadline=None)
@given(text=st.text(max_size=60), base=st.sampled_from(["https://a.com/x", "http://a.com:81/"]))
def test_resolve_location_raises_only_scope_violation_when_location_is_any_text(
    text: str, base: str
) -> None:
    with contextlib.suppress(ScopeViolation):
        resolve_location(base_url=base, location=text)


@pytest.mark.parametrize("method", sorted(KNOWN_METHODS))
def test_normalize_request_accepts_each_known_method(method: str) -> None:
    assert normalize_request(method, "https://a.com/").method == method


@pytest.mark.parametrize("method", ["TRACE", "CONNECT", "get", "", "GET ", None, 1, b"GET"])
def test_normalize_request_rejects_when_method_is_not_in_known_set(method: object) -> None:
    with pytest.raises(ScopeViolation):
        normalize_request(method, "https://a.com/")  # type: ignore[arg-type]  # entrada hostil de propósito


def test_normalize_request_exposes_effective_port_and_canonical_origin() -> None:
    request = normalize_request("GET", "HTTPS://A.com:443/x/")

    assert (request.scheme, request.port, request.host.text) == ("https", 443, "a.com")
    assert request.origin == "https://a.com"
    assert request.path == "/x"
    assert normalize_request("GET", "http://a.com:8080/").origin == "http://a.com:8080"


def test_normalize_request_decodes_path_exactly_once() -> None:
    assert normalize_request("GET", "https://a.com/%41%62").segments == ("Ab",)
    with pytest.raises(ScopeViolation):
        normalize_request("GET", "https://a.com/%2541")


def test_normalize_request_accepts_literal_space_only_through_percent_encoding() -> None:
    assert normalize_request("GET", "https://a.com/a%20b").segments == ("a b",)
    with pytest.raises(ScopeViolation):
        normalize_request("GET", "https://a.com/a b")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a.com.", "a.com"),
        ("A.Com", "a.com"),
        ("xn--80ak6aa92e.com", "xn--80ak6aa92e.com"),
        ("пример.рф", "xn--e1afmkfd.xn--p1ai"),
        ("[0:0:0:0:0:0:0:1]", "[::1]"),
        ("[2001:DB8::1]", "[2001:db8::1]"),
        ("1.2.3.4", "1.2.3.4"),
    ],
)
def test_parse_host_returns_canonical_text_when_host_is_equivalent(raw: str, expected: str) -> None:
    assert parse_host(raw).text == expected


def test_parse_host_treats_cyrillic_lookalike_as_a_different_host() -> None:
    assert parse_host("аllowed.com") != parse_host("allowed.com")


def test_parse_host_error_is_truncated_when_host_is_very_long() -> None:
    with pytest.raises(ScopeViolation) as caught:
        parse_host("a" * 5000 + "_.com")

    assert len(caught.value.message) < 500


def test_parse_host_accepts_label_of_63_and_name_of_253_but_not_beyond() -> None:
    label = "a" * 63
    parse_host(f"{label}.com")
    parse_host(".".join(["a" * 61] * 4))  # 4*61+3 = 247
    with pytest.raises(ScopeViolation):
        parse_host("a" * 64 + ".com")
    with pytest.raises(ScopeViolation):
        parse_host(".".join(["a" * 62] * 4 + ["bb"]))  # > 253
