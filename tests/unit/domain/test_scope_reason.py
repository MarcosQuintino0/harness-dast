"""Códigos estáveis de recusa (`ScopeReason`) vindos da normalização e do `ScopeGuard`."""

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.pathpattern import matches
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule
from harness_dast.domain.scope_reason import PATH_SHAPE_CODES, ScopeReason
from harness_dast.domain.urlnorm import normalize_request

BASE = "https://api.permitido.com"
GUARD = ScopeGuard(
    Scope(
        allow=(ScopeRule(host="api.permitido.com", paths=("/api/**",), methods=("GET",)),),
        deny_paths=("/api/admin/**",),
    )
)


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("get", f"{BASE}/api/x", ScopeReason.METHOD_UNKNOWN),
        ("GET", "", ScopeReason.URL_MISSING),
        ("GET", f"{BASE}/" + "a" * 2100, ScopeReason.URL_TOO_LONG),
        ("GET", f"{BASE}/api/a b", ScopeReason.URL_FORBIDDEN_CHAR),
        ("GET", f"{BASE}/api\\x", ScopeReason.URL_FORBIDDEN_CHAR),
        ("GET", "/api/x", ScopeReason.URL_NOT_ABSOLUTE),
        ("GET", f"{BASE}/api/café", ScopeReason.URL_NOT_ASCII),
        ("GET", "ftp://api.permitido.com/x", ScopeReason.SCHEME_NOT_ALLOWED),
        ("GET", "https://u@api.permitido.com/x", ScopeReason.CREDENTIALS_IN_URL),
        ("GET", "https://api.permitido.com:99999/x", ScopeReason.PORT_INVALID),
        ("GET", "https://api.permitido.com:abc/x", ScopeReason.PORT_INVALID),
        ("GET", "https://0x7f.1/x", ScopeReason.HOST_INVALID),
        ("GET", "https://[::1/x", ScopeReason.HOST_INVALID),
        ("GET", f"{BASE}/api//x", ScopeReason.PATH_EMPTY_SEGMENT),
        ("GET", f"{BASE}/api/%zz", ScopeReason.PATH_BAD_PERCENT),
        ("GET", f"{BASE}/api/%ff", ScopeReason.PATH_INVALID_UTF8),
        ("GET", f"{BASE}/api/%252e", ScopeReason.PATH_DOUBLE_ENCODING),
        ("GET", f"{BASE}/api/a%2fb", ScopeReason.PATH_ENCODED_SLASH),
        ("GET", f"{BASE}/api/a%5cb", ScopeReason.PATH_ENCODED_SLASH),
        ("GET", f"{BASE}/api/a%00", ScopeReason.PATH_CONTROL_CHAR),
        ("GET", f"{BASE}/api/%c2%a0", ScopeReason.PATH_CONTROL_CHAR),
        ("GET", f"{BASE}/api/../x", ScopeReason.PATH_DOT_SEGMENT),
        ("GET", f"{BASE}/api/..;/x", ScopeReason.PATH_DOT_SEGMENT),
        ("GET", f"{BASE}/api/a;b", ScopeReason.PATH_MATRIX_PARAM),
        ("GET", f"{BASE}/api/a.", ScopeReason.PATH_TRAILING_DOT_SPACE),
        ("GET", f"{BASE}/api/a%20", ScopeReason.PATH_TRAILING_DOT_SPACE),
    ],
)
def test_normalize_request_carries_a_stable_reason_code(
    method: str, url: str, reason: ScopeReason
) -> None:
    with pytest.raises(ScopeViolation) as caught:
        normalize_request(method, url)

    assert caught.value.reason is reason


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("GET", f"{BASE}/api/admin/x", ScopeReason.DENY_PATH),
        ("GET", "https://outro.com/api/x", ScopeReason.HOST_NOT_ALLOWED),
        ("GET", "http://api.permitido.com/api/x", ScopeReason.ORIGIN_NOT_ALLOWED),
        ("GET", f"{BASE}/fora", ScopeReason.PATH_NOT_ALLOWED),
        ("POST", f"{BASE}/api/x", ScopeReason.METHOD_NOT_ALLOWED),
    ],
)
def test_scope_guard_carries_a_stable_reason_code_for_scope_decisions(
    method: str, url: str, reason: ScopeReason
) -> None:
    with pytest.raises(ScopeViolation) as caught:
        GUARD.ensure_allowed(OutboundRequest(method=method, url=url))

    assert caught.value.reason is reason
    assert not reason.is_malformed


def test_violation_without_reason_has_none() -> None:
    assert ScopeViolation("fora da janela").reason is None


def test_every_non_decision_code_is_malformed_and_path_shape_codes_start_with_path() -> None:
    decisions = {
        ScopeReason.DENY_PATH,
        ScopeReason.ORIGIN_NOT_ALLOWED,
        ScopeReason.HOST_NOT_ALLOWED,
        ScopeReason.PATH_NOT_ALLOWED,
        ScopeReason.METHOD_NOT_ALLOWED,
    }

    assert {r for r in ScopeReason if not r.is_malformed} == decisions
    assert ScopeReason.PATH_NOT_ALLOWED.value not in PATH_SHAPE_CODES
    assert ScopeReason.PATH_ENCODED_SLASH.value in PATH_SHAPE_CODES
    assert ScopeReason.URL_FORBIDDEN_CHAR.value not in PATH_SHAPE_CODES


# ---- Sufixo de formato (ADR 0026): comportamento ATUAL do modo estrito, fixado por teste.


@pytest.mark.parametrize("suffix", [".json", ".xml", ".html", ".tar.gz"])
def test_strict_guard_does_not_cover_format_suffix(suffix: str) -> None:
    # `deny_paths: /api/admin/**` casa o segmento inteiro `admin`; `admin.json` é outro
    # segmento. Servidores que roteiam `/admin.json` para o handler de `/admin` passam.
    outcome = GUARD.evaluate(OutboundRequest(method="GET", url=f"{BASE}/api/admin{suffix}"))

    assert outcome.verdict == "allowed"


def test_matches_treats_an_exact_segment_as_different_from_one_with_suffix() -> None:
    assert not matches(("api", "admin"), ("api", "admin.json"), fold=True)


def test_wildcard_does_not_match_an_empty_segment_when_asked_not_to() -> None:
    assert matches(("a", "*"), ("a", ""))
    assert not matches(("a", "*"), ("a", ""), wildcard_matches_empty=False)
    assert matches(("a", "**"), ("a", ""), wildcard_matches_empty=False)
