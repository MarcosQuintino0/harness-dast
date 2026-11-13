import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.adapters.scope_proxy.decision import ALLOW, Reason, ScopeDecider, classify
from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.scope import OutboundRequest, ScopeGuard
from tests.unit.adapters.scope_proxy.helpers import make_policy

POLICY = make_policy()
DECIDER = ScopeDecider(POLICY.scope)
GUARD = ScopeGuard(POLICY.scope)
BASE = "https://api.exemplo.com"


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("GET", f"{BASE}/api/users", Reason.ALLOWED),
        ("POST", f"{BASE}/api/users?token=segredo", Reason.ALLOWED),
        ("GET", "http://vampi:5000/users/v1", Reason.ALLOWED),
        ("GET", f"{BASE}/api/admin/x", Reason.DENY_PATH),
        ("GET", f"{BASE}/API/ADMIN/x", Reason.DENY_PATH),
        ("GET", "https://outro.exemplo.com/api/users", Reason.HOST_NOT_ALLOWED),
        ("GET", "http://api.exemplo.com/api/users", Reason.ORIGIN_NOT_ALLOWED),
        ("GET", "https://api.exemplo.com:8443/api/users", Reason.ORIGIN_NOT_ALLOWED),
        ("GET", "http://vampi:5001/users/v1", Reason.ORIGIN_NOT_ALLOWED),
        ("GET", f"{BASE}/fora", Reason.PATH_NOT_ALLOWED),
        ("DELETE", f"{BASE}/api/users", Reason.METHOD_NOT_ALLOWED),
        ("POST", "http://vampi:5000/users/v1", Reason.METHOD_NOT_ALLOWED),
    ],
)
def test_decide_request_devolve_o_motivo_esperado(method: str, url: str, reason: Reason) -> None:
    verdict = DECIDER.decide_request(method, url)

    assert verdict.reason is reason
    assert verdict.allowed is (reason is Reason.ALLOWED)


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/api/admin;x=1",
        f"{BASE}/api/admin.",
        f"{BASE}/api/%2e%2e/admin",
        f"{BASE}/api//users",
        f"{BASE}/api/users%2fadmin",
        "https://api.exemplo.com@evil.com/api/users",
        "https://169.254.169.254/latest/meta-data/",
        "https://0x7f.1/api/users",
        "ftp://api.exemplo.com/api/users",
        "/api/users",
        "",
    ],
)
def test_decide_request_recusa_url_malformada_ou_ambigua(url: str) -> None:
    verdict = DECIDER.decide_request("GET", url)

    assert verdict.allowed is False
    assert verdict.reason is Reason.MALFORMED_REQUEST


@pytest.mark.parametrize("method", ["get", "CONNECT", "TRACE", "", "GET "])
def test_decide_request_recusa_metodo_desconhecido(method: str) -> None:
    verdict = DECIDER.decide_request(method, f"{BASE}/api/users")

    assert verdict == DECIDER.decide_request(method, f"{BASE}/api/users")
    assert verdict.allowed is False
    assert verdict.reason is Reason.MALFORMED_REQUEST


def test_decide_connect_permite_host_e_porta_de_regra_https() -> None:
    assert DECIDER.decide_connect("api.exemplo.com", 443) == ALLOW


@pytest.mark.parametrize(
    ("host", "port", "reason"),
    [
        ("outro.exemplo.com", 443, Reason.HOST_NOT_ALLOWED),
        ("api.exemplo.com", 8443, Reason.ORIGIN_NOT_ALLOWED),
        # A regra do vampi é http: um túnel TLS para ela não tem regra que o cubra.
        ("vampi", 5000, Reason.ORIGIN_NOT_ALLOWED),
        ("169.254.169.254", 443, Reason.MALFORMED_REQUEST),
        ("10.0.0.1", 443, Reason.HOST_NOT_ALLOWED),
        ("api.exemplo.com/x", 443, Reason.MALFORMED_REQUEST),
        ("", 443, Reason.MALFORMED_REQUEST),
        ("::1", 443, Reason.HOST_NOT_ALLOWED),
        ("api.exemplo.com?x", 443, Reason.MALFORMED_REQUEST),
        ("evil.com@api.exemplo.com", 443, Reason.MALFORMED_REQUEST),
        ("api.exemplo.com\\x", 443, Reason.MALFORMED_REQUEST),
        ("api.exemplo.com ", 443, Reason.MALFORMED_REQUEST),
    ],
)
def test_decide_connect_recusa_com_motivo(host: str, port: int, reason: Reason) -> None:
    verdict = DECIDER.decide_connect(host, port)

    assert verdict.allowed is False
    assert verdict.reason is reason


def test_classify_cai_em_malformed_quando_a_mensagem_e_desconhecida() -> None:
    assert classify(ScopeViolation("mensagem nova do guarda")) is Reason.MALFORMED_REQUEST


# ---- Propriedade: o decisor nunca diverge do ScopeGuard.
_HOSTS = ["api.exemplo.com", "vampi", "outro.exemplo.com", "169.254.169.254", "10.0.0.1"]
_SCHEMES = ["http", "https", "ftp"]
_PORTS = ["", ":443", ":5000", ":80", ":8443", ":0"]
_SEGMENTS = ["api", "admin", "users", "ADMIN", "..", ".", "%2e", "a;b", "x.", "", "v1", "%2F", "é"]
_METHODS = ["GET", "POST", "PUT", "DELETE", "get", "CONNECT", "HEAD", ""]


@st.composite
def requests(draw: st.DrawFn) -> tuple[str, str]:
    scheme = draw(st.sampled_from(_SCHEMES))
    host = draw(st.sampled_from(_HOSTS))
    port = draw(st.sampled_from(_PORTS))
    path = "/".join(draw(st.lists(st.sampled_from(_SEGMENTS), max_size=4)))
    query = draw(st.sampled_from(["", "?a=1", "?token=x&y"]))
    return draw(st.sampled_from(_METHODS)), f"{scheme}://{host}{port}/{path}{query}"


def _guard_allows(method: str, url: str) -> bool:
    try:
        GUARD.ensure_allowed(OutboundRequest(method=method, url=url))
    except ScopeViolation:
        return False
    return True


@settings(max_examples=400, deadline=None)
@given(requests())
def test_decide_request_permite_se_e_somente_se_o_scope_guard_permite(
    request: tuple[str, str],
) -> None:
    method, url = request

    assert DECIDER.decide_request(method, url).allowed is _guard_allows(method, url)
