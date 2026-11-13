import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.urlnorm import (
    MAX_URL_LENGTH,
    NormalizedRequest,
    default_port,
    normalize_request,
    resolve_location,
)


def test_normalize_request_lowercases_host_and_drops_trailing_dot_when_host_is_noisy() -> None:
    result = normalize_request("GET", "https://API.Permitido.COM./api/x")

    assert result.host.text == "api.permitido.com"


def test_normalize_request_uses_default_port_when_url_has_no_port() -> None:
    assert normalize_request("GET", "https://a.com/x").port == 443
    assert normalize_request("GET", "http://a.com/x").port == 80


def test_normalize_request_keeps_explicit_port_when_url_has_one() -> None:
    assert normalize_request("GET", "https://a.com:8443/x").port == 8443


def test_normalize_request_decodes_unreserved_escape_once_when_path_is_encoded() -> None:
    assert normalize_request("GET", "https://a.com/%61pi/x").segments == ("api", "x")


def test_normalize_request_ignores_query_and_fragment_when_deciding_path() -> None:
    result = normalize_request("GET", "https://a.com/x?next=//evil.com#frag")

    assert result.segments == ("x",)


def test_normalize_request_treats_trailing_slash_as_same_path_when_present() -> None:
    assert normalize_request("GET", "https://a.com/x/").segments == ("x",)


def test_normalize_request_yields_empty_segments_when_path_is_root_or_missing() -> None:
    assert normalize_request("GET", "https://a.com").segments == ()
    assert normalize_request("GET", "https://a.com/").segments == ()


def test_normalize_request_allows_encoded_space_when_segment_has_plain_space() -> None:
    assert normalize_request("GET", "https://a.com/my%20cat").segments == ("my cat",)


@pytest.mark.parametrize(
    ("method", "url", "fragment"),
    [
        pytest.param("GET", "ftp://a.com/x", "Esquema", id="ftp_scheme"),
        pytest.param("GET", "file:///etc/passwd", "Esquema", id="file_scheme"),
        pytest.param("GET", "gopher://a.com/x", "Esquema", id="gopher_scheme"),
        pytest.param("GET", "javascript:alert(1)", "absoluta", id="javascript_pseudo_url"),
        pytest.param("GET", "//a.com/x", "absoluta", id="scheme_relative"),
        pytest.param("GET", "a.com/x", "absoluta", id="no_scheme"),
        pytest.param("GET", "/x", "absoluta", id="path_only"),
        pytest.param("GET", "", "ausente", id="empty_url"),
        pytest.param("GET", "http:///x", "Host ausente", id="missing_host"),
        pytest.param("GET", "https://:443/x", "Host ausente", id="missing_host_with_port"),
        pytest.param("GET", "https://a.com@b.com/x", "Credenciais", id="userinfo_allowed_first"),
        pytest.param("GET", "https://b.com@a.com/x", "Credenciais", id="userinfo_allowed_last"),
        pytest.param("GET", "https://u:p@a.com/x", "Credenciais", id="userinfo_with_password"),
        pytest.param("GET", "https://a.com:/x", "Porta", id="empty_port"),
        pytest.param("GET", "https://a.com:0/x", "Porta", id="port_zero"),
        pytest.param("GET", "https://a.com:65536/x", "Porta", id="port_too_big"),
        pytest.param("GET", "https://a.com:0443/x", "Porta", id="port_leading_zero"),
        pytest.param("GET", "https://a.com:4x3/x", "Porta", id="port_not_numeric"),
        pytest.param("GET", "https://a.com:443:80/x", "Porta", id="two_ports"),
        pytest.param("GET", "https://a.com:٤٤٣/x", "Porta", id="arabic_digit_port"),
        pytest.param("GET", "https://a.com/a b", "controle", id="space_in_path"),
        pytest.param("GET", "https://a.com/a\tb", "controle", id="tab_in_path"),
        pytest.param("GET", "https://a.com/a\nb", "controle", id="newline_in_path"),
        pytest.param("GET", "https://a.com/a\rb", "controle", id="carriage_return_in_path"),
        pytest.param("GET", "https://a.com/a\x00b", "controle", id="nul_in_path"),
        pytest.param("GET", " https://a.com/x", "controle", id="leading_space"),
        pytest.param("GET", "https://a.com/x\u200b", "controle", id="zero_width_space"),
        pytest.param("GET", "https://a.com/\u202egnp.x", "controle", id="bidi_override"),
        pytest.param("GET", "https://a.com\\@b.com/x", "controle", id="backslash_in_authority"),
        pytest.param("GET", "https://a.com/a\\b", "controle", id="backslash_in_path"),
        pytest.param("GET", "https://a.com/café", "ASCII", id="non_ascii_path"),
        pytest.param("GET", "https://a.com/x?q=é", "ASCII", id="non_ascii_query"),
        pytest.param("GET", "https://a.com/x?q=a b", "controle", id="space_in_query"),
        pytest.param("GET", "https://a.com/" + "a" * MAX_URL_LENGTH, "maior", id="url_too_long"),
        pytest.param("GET", "https://a.com//x", "vazio", id="double_slash_in_path"),
        pytest.param("GET", "https://a.com/x//", "vazio", id="double_trailing_slash"),
        pytest.param("GET", "https://a.com/a/../b", "travessia", id="dotdot"),
        pytest.param("GET", "https://a.com/a/./b", "travessia", id="dot"),
        pytest.param("GET", "https://a.com/%2e%2e/b", "travessia", id="encoded_dotdot"),
        pytest.param("GET", "https://a.com/%2E%2E/b", "travessia", id="encoded_dotdot_upper"),
        pytest.param("GET", "https://a.com/.%2e/b", "travessia", id="mixed_dotdot"),
        pytest.param("GET", "https://a.com/..;/b", "travessia", id="dotdot_with_path_parameter"),
        pytest.param("GET", "https://a.com/%2e;x/b", "travessia", id="dot_with_path_parameter"),
        pytest.param("GET", "https://a.com/%252e%252e/b", "dupla", id="double_encoded_dotdot"),
        pytest.param("GET", "https://a.com/a%25b", "dupla", id="encoded_percent_sign"),
        pytest.param("GET", "https://a.com/a%2fb", "barra", id="encoded_slash"),
        pytest.param("GET", "https://a.com/a%2Fb", "barra", id="encoded_slash_upper"),
        pytest.param("GET", "https://a.com/a%5cb", "barra", id="encoded_backslash"),
        pytest.param("GET", "https://a.com/a%00b", "barra", id="encoded_nul"),
        pytest.param("GET", "https://a.com/a%0ab", "barra", id="encoded_newline"),
        pytest.param("GET", "https://a.com/a%09b", "barra", id="encoded_tab"),
        pytest.param("GET", "https://a.com/a%zzb", "malformada", id="bad_percent_escape"),
        pytest.param("GET", "https://a.com/a%", "malformada", id="truncated_percent_escape"),
        pytest.param("GET", "https://a.com/a%ffb", "UTF-8", id="invalid_utf8"),
        pytest.param("get", "https://a.com/x", "Método", id="lowercase_method"),
        pytest.param("TRACE", "https://a.com/x", "Método", id="trace_method"),
        pytest.param("CONNECT", "https://a.com/x", "Método", id="connect_method"),
        pytest.param("", "https://a.com/x", "Método", id="empty_method"),
        pytest.param("GET ", "https://a.com/x", "Método", id="method_with_space"),
    ],
)
def test_normalize_request_rejects_when_input_is_ambiguous_or_unsafe(
    method: str, url: str, fragment: str
) -> None:
    with pytest.raises(ScopeViolation, match=fragment) as caught:
        normalize_request(method, url)

    assert caught.value.hint


def test_normalize_request_does_not_echo_secrets_when_url_has_credentials() -> None:
    with pytest.raises(ScopeViolation) as caught:
        normalize_request("GET", "https://admin:hunter2@a.com/x?token=abc123")

    assert "hunter2" not in caught.value.message
    assert "abc123" not in caught.value.message


def test_default_port_is_443_for_https_and_80_for_http() -> None:
    assert default_port("https") == 443
    assert default_port("http") == 80


def test_origin_omits_default_port_and_keeps_other_ports() -> None:
    assert normalize_request("GET", "https://a.com:443/x").origin == "https://a.com"
    assert normalize_request("GET", "https://a.com:8443/x").origin == "https://a.com:8443"


def test_resolve_location_inherits_origin_when_location_is_path_absolute() -> None:
    assert (
        resolve_location(base_url="https://a.com:8443/x", location="/y") == "https://a.com:8443/y"
    )


def test_resolve_location_inherits_scheme_when_location_is_scheme_relative() -> None:
    assert resolve_location(base_url="https://a.com/x", location="//b.com/y") == "https://b.com/y"


def test_resolve_location_returns_absolute_location_unchanged() -> None:
    assert (
        resolve_location(base_url="https://a.com/x", location="http://b.com/y") == "http://b.com/y"
    )


def test_resolve_location_rejects_when_base_url_is_invalid() -> None:
    with pytest.raises(ScopeViolation):
        resolve_location(base_url="not a url", location="/y")


def test_resolve_location_rejects_when_location_has_control_characters() -> None:
    with pytest.raises(ScopeViolation):
        resolve_location(base_url="https://a.com/x", location="/y\r\nSet-Cookie: a=b")


# ----------------------------------------------------------------- propriedades

_SEGMENT = st.one_of(
    st.sampled_from(["api", "x", "%61pi", "my%20cat", "a%3Bb", "..", ".", "%2e%2e", "", "a%2fb"]),
    st.text(alphabet="abcXYZ09%2eEfF/;._-~ ", max_size=6),
)
_HOST = st.one_of(
    st.sampled_from(["a.com", "A.COM", "a.com.", "127.0.0.1", "[::1]", "xn--mnchen-3ya.de"]),
    st.text(alphabet="abc.-:@[]0123456789", max_size=12),
)


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp"]),
    host=_HOST,
    port=st.one_of(st.just(""), st.integers(0, 70000).map(lambda n: f":{n}")),
    segments=st.lists(_SEGMENT, max_size=5),
    method=st.sampled_from(["GET", "POST", "get"]),
)
def test_normalization_is_idempotent_when_request_is_accepted(
    scheme: str, host: str, port: str, segments: list[str], method: str
) -> None:
    url = f"{scheme}://{host}{port}/" + "/".join(segments)
    try:
        first = normalize_request(method, url)
    except ScopeViolation:
        return

    second = normalize_request(first.method, first.url)

    assert second == first


@settings(max_examples=500, deadline=None)
@given(url=st.text(max_size=80))
def test_normalize_request_fails_closed_when_input_is_arbitrary_text(url: str) -> None:
    try:
        result = normalize_request("GET", url)
    except ScopeViolation:
        return

    assert isinstance(result, NormalizedRequest)
    assert result.scheme in {"http", "https"}


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        pytest.param("/admin;x=1", "parâmetro", id="matrix_parameter"),
        pytest.param("/admin%3Bx=1", "parâmetro", id="encoded_semicolon"),
        pytest.param("/admin%3b", "parâmetro", id="encoded_semicolon_lowercase"),
        pytest.param("/admin;/x", "parâmetro", id="semicolon_before_slash"),
        pytest.param("/a/;/b", "parâmetro", id="semicolon_only_segment"),
        pytest.param("/admin.", "ponto ou espaço", id="trailing_dot"),
        pytest.param("/admin..", "ponto ou espaço", id="trailing_double_dot"),
        pytest.param("/admin%2e", "ponto ou espaço", id="encoded_trailing_dot"),
        pytest.param("/admin%2E", "ponto ou espaço", id="encoded_trailing_dot_upper"),
        pytest.param("/admin%20", "ponto ou espaço", id="encoded_trailing_space"),
        pytest.param("/%20admin", "ponto ou espaço", id="encoded_leading_space"),
        pytest.param("/admin%20./x", "ponto ou espaço", id="space_dot_in_middle_segment"),
        pytest.param("/admin%09", "espaço invisível", id="trailing_tab"),
        pytest.param("/admin%0a", "espaço invisível", id="trailing_newline"),
        pytest.param("/admin%00", "espaço invisível", id="trailing_nul"),
        pytest.param("/admin%a0", "UTF-8", id="trailing_latin1_nbsp_invalid_utf8"),
        pytest.param("/admin%c2%a0", "espaço invisível", id="trailing_nbsp"),
    ],
)
def test_normalize_request_rejects_when_server_may_rewrite_the_path_before_routing(
    path: str, fragment: str
) -> None:
    with pytest.raises(ScopeViolation, match=fragment):
        normalize_request("GET", "https://a.com" + path)


@pytest.mark.parametrize("path", ["/v1.0/items", "/file.json", "/a.b.c", "/my%20cat", "/a-b_c"])
def test_normalize_request_keeps_legitimate_dots_and_spaces_inside_a_segment(path: str) -> None:
    assert normalize_request("GET", "https://a.com" + path).segments


def test_normalize_request_does_not_echo_path_in_rewrite_errors() -> None:
    with pytest.raises(ScopeViolation) as caught:
        normalize_request("GET", "https://a.com/SEGREDO-123;x")

    assert "SEGREDO" not in caught.value.message
