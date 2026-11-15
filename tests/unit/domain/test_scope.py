from urllib.parse import unquote

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule

HOST = "api.permitido.com"
BASE = f"https://{HOST}"


def make_rule(**changes: object) -> ScopeRule:
    data: dict[str, object] = {"host": HOST, "paths": ["/api/**"], "methods": ["GET", "POST"]}
    data.update(changes)
    return ScopeRule.model_validate(data)


def make_scope(
    *rules: ScopeRule, deny: tuple[str, ...] = ("/api/admin/**", "/api/conta/excluir")
) -> Scope:
    return Scope(allow=rules or (make_rule(),), deny_paths=deny)


def make_guard(
    *rules: ScopeRule, deny: tuple[str, ...] = ("/api/admin/**", "/api/conta/excluir")
) -> ScopeGuard:
    return ScopeGuard(make_scope(*rules, deny=deny))


def check(guard: ScopeGuard, method: str, url: str) -> None:
    guard.ensure_allowed(OutboundRequest(method=method, url=url))


# ---------------------------------------------------------- regras de permissão


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("*.permitido.com", id="wildcard_prefix"),
        pytest.param("*", id="only_wildcard"),
        pytest.param("api.*.com", id="wildcard_middle"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param("https://api.permitido.com", id="has_scheme"),
        pytest.param("api.permitido.com:8443", id="has_port"),
        pytest.param("user@api.permitido.com", id="has_userinfo"),
        pytest.param("api.permitido.com/api", id="has_path"),
        pytest.param("api.permitido.com?x=1", id="has_query"),
        pytest.param("api.permitido.com#x", id="has_fragment"),
        pytest.param("api.permitido.com\\x", id="has_backslash"),
        pytest.param("api%2epermitido.com", id="has_percent"),
        pytest.param("xn--zz.example", id="invalid_punycode"),
        pytest.param("2130706433", id="decimal_ip"),
        pytest.param("93.184.216.34", id="public_ip_literal"),
        pytest.param("[2001:db8::1]", id="public_ipv6_literal"),
        pytest.param("169.254.169.254", id="metadata_ip"),
    ],
)
def test_rule_rejects_host_when_it_is_dangerous_or_ambiguous(host: str) -> None:
    with pytest.raises(ValidationError):
        make_rule(host=host)


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("127.0.0.1", id="loopback_ip"),
        pytest.param("10.0.0.5", id="private_ip"),
        pytest.param("[::1]", id="loopback_v6"),
        pytest.param("localhost", id="localhost"),
        pytest.param("vampi", id="docker_service_name"),
        pytest.param("host.docker.internal", id="docker_internal_name"),
    ],
)
def test_rule_requires_allow_local_when_host_is_local(host: str) -> None:
    with pytest.raises(ValidationError, match="allow_local"):
        make_rule(host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "[::1]", "localhost", "vampi"])
def test_rule_accepts_local_host_when_allow_local_is_explicit(host: str) -> None:
    rule = make_rule(host=host, allow_local=True, scheme="http")

    assert rule.allow_local is True


def test_rule_rejects_allow_local_when_host_is_public() -> None:
    with pytest.raises(ValidationError, match="allow_local só se aplica"):
        make_rule(allow_local=True)


@pytest.mark.parametrize("host", ["169.254.169.254", "169.254.10.10", "0.0.0.0", "[fe80::1]"])  # noqa: S104 - caso de teste
def test_rule_rejects_forbidden_ip_even_when_allow_local_is_set(host: str) -> None:
    with pytest.raises(ValidationError):
        make_rule(host=host, allow_local=True)


def test_rule_rejects_public_ip_even_when_allow_local_is_set() -> None:
    with pytest.raises(ValidationError, match="IP público"):
        make_rule(host="93.184.216.34", allow_local=True)


def test_rule_canonicalizes_host_when_written_with_case_dot_or_unicode() -> None:
    assert make_rule(host="API.Permitido.COM.").host == HOST
    assert make_rule(host="münchen.example").host == "xn--mnchen-3ya.example"


@pytest.mark.parametrize(
    "methods",
    [
        pytest.param([], id="empty"),
        pytest.param(["get"], id="lowercase"),
        pytest.param(["TRACE"], id="trace"),
        pytest.param(["CONNECT"], id="connect"),
        pytest.param(["FETCH"], id="unknown"),
        pytest.param(["GET", "ALL"], id="one_unknown_among_valid"),
        pytest.param([""], id="empty_string"),
    ],
)
def test_rule_rejects_methods_when_unknown_or_empty(methods: list[str]) -> None:
    with pytest.raises(ValidationError):
        make_rule(methods=methods)


def test_rule_sorts_and_deduplicates_methods_when_given_repeats() -> None:
    assert make_rule(methods=["POST", "GET", "POST"]).methods == ("GET", "POST")


@pytest.mark.parametrize(
    "paths",
    [
        pytest.param([], id="empty_list"),
        pytest.param(["api/**"], id="no_leading_slash"),
        pytest.param([""], id="empty_pattern"),
        pytest.param(["/api/../x"], id="dotdot"),
        pytest.param(["/api/us*"], id="partial_wildcard"),
        pytest.param(["/api//x"], id="empty_segment"),
    ],
)
def test_rule_rejects_paths_when_pattern_is_invalid_or_list_is_empty(paths: list[str]) -> None:
    with pytest.raises(ValidationError):
        make_rule(paths=paths)


@pytest.mark.parametrize("port", [0, -1, 65536, True, "443"])
def test_rule_rejects_port_when_out_of_range_or_wrong_type(port: object) -> None:
    with pytest.raises(ValidationError):
        make_rule(port=port)


def test_rule_rejects_unknown_scheme_and_unknown_field() -> None:
    with pytest.raises(ValidationError):
        make_rule(scheme="ftp")
    with pytest.raises(ValidationError):
        make_rule(metohds=["GET"])  # campo com erro de digitação


def test_rule_rejects_allow_local_when_value_is_not_a_real_boolean() -> None:
    with pytest.raises(ValidationError):
        make_rule(host="localhost", allow_local="yes")


def test_rule_is_frozen_when_attribute_assignment_is_attempted() -> None:
    rule = make_rule()

    with pytest.raises(ValidationError):
        rule.host = "outro.com"  # type: ignore[misc]  # prova que o modelo é congelado


def test_scope_rejects_empty_allow_list_when_no_rule_is_given() -> None:
    with pytest.raises(ValidationError):
        Scope(allow=())


def test_scope_rejects_invalid_deny_pattern_when_pattern_has_dotdot() -> None:
    with pytest.raises(ValidationError):
        Scope(allow=(make_rule(),), deny_paths=("/api/../x",))


# ------------------------------------------------------------------ positivos


@pytest.mark.parametrize(
    ("method", "url"),
    [
        pytest.param("GET", f"{BASE}/api/users", id="simple_get"),
        pytest.param("POST", f"{BASE}/api/users", id="allowed_post"),
        pytest.param("GET", f"{BASE}/api", id="double_star_base"),
        pytest.param("GET", f"{BASE}/api/a/b/c/d", id="deep_path"),
        pytest.param("GET", "https://API.PERMITIDO.COM/api/users", id="host_uppercase"),
        pytest.param("GET", "https://Api.Permitido.Com/api/users", id="host_mixed_case"),
        pytest.param("GET", f"{BASE}./api/users", id="host_trailing_dot"),
        pytest.param("GET", f"{BASE}:443/api/users", id="explicit_default_port"),
        pytest.param("GET", f"{BASE}/api/users?next=//evil.com", id="query_ignored"),
        pytest.param("GET", f"{BASE}/api/users#//evil.com", id="fragment_ignored"),
        pytest.param("GET", f"{BASE}/api/users/", id="trailing_slash"),
        pytest.param("GET", f"{BASE}/api/%75sers", id="encoded_unreserved_letter"),
        pytest.param("GET", f"{BASE}/api/my%20cat", id="encoded_space"),
        pytest.param("GET", "HTTPS://api.permitido.com/api/users", id="scheme_uppercase"),
    ],
)
def test_guard_allows_request_when_it_matches_an_explicit_rule(method: str, url: str) -> None:
    check(make_guard(), method, url)


# ------------------------------------------------------------------ bypass


BYPASS_CASES = [
    # host fora da lista
    ("GET", "https://outro.com/api/x", "não está em scope.allow", "other_host"),
    (
        "GET",
        "https://evil.api.permitido.com/api/x",
        "não está em scope.allow",
        "subdomain_of_allowed",
    ),
    ("GET", "https://permitido.com/api/x", "não está em scope.allow", "parent_domain_of_allowed"),
    (
        "GET",
        "https://api.permitido.com.evil.com/api/x",
        "não está em scope.allow",
        "allowed_as_prefix",
    ),
    (
        "GET",
        "https://xapi.permitido.com/api/x",
        "não está em scope.allow",
        "allowed_with_extra_letter",
    ),
    # userinfo
    ("GET", f"https://{HOST}@outro.com/api/x", "Credenciais", "userinfo_allowed_before_at"),
    ("GET", f"https://outro.com@{HOST}/api/x", "Credenciais", "userinfo_other_before_at"),
    ("GET", f"https://user:pass@{HOST}/api/x", "Credenciais", "userinfo_with_password"),
    ("GET", f"https://{HOST}%40outro.com@{HOST}/api/x", "Credenciais", "userinfo_encoded_at"),
    (
        "GET",
        "https://api.permitido.com\uff20outro.com/api/x",
        "não permitidos|canônica",
        "fullwidth_at",
    ),
    # IPs
    ("GET", "https://127.0.0.1/api/x", "não está em scope.allow", "ipv4_loopback"),
    ("GET", "https://10.0.0.5/api/x", "não está em scope.allow", "ipv4_private"),
    ("GET", "https://192.168.1.1/api/x", "não está em scope.allow", "ipv4_private_192"),
    ("GET", "https://172.16.0.1/api/x", "não está em scope.allow", "ipv4_private_172"),
    ("GET", "https://93.184.216.34/api/x", "não está em scope.allow", "ipv4_public"),
    ("GET", "https://[::1]/api/x", "não está em scope.allow", "ipv6_loopback"),
    ("GET", "https://[2001:db8::1]/api/x", "não está em scope.allow", "ipv6_public"),
    ("GET", "https://[::ffff:127.0.0.1]/api/x", "embute IPv4", "ipv6_mapped_loopback"),
    ("GET", "https://[::ffff:7f00:1]/api/x", "embute IPv4", "ipv6_mapped_hex"),
    ("GET", "https://169.254.169.254/latest/meta-data/", "metadados", "cloud_metadata_ipv4"),
    ("GET", "http://169.254.169.254/latest/meta-data/", "metadados", "cloud_metadata_http"),
    ("GET", "https://[fd00:ec2::254]/latest/meta-data/", "metadados", "cloud_metadata_ipv6"),
    (
        "GET",
        "https://metadata.google.internal/computeMetadata/v1/",
        "metadados",
        "gcp_metadata_name",
    ),
    ("GET", "https://169.254.10.1/api/x", "faixa proibida", "link_local_ipv4"),
    ("GET", "https://[fe80::1]/api/x", "faixa proibida", "link_local_ipv6"),
    ("GET", "https://0.0.0.0/api/x", "faixa proibida", "unspecified_ipv4"),
    ("GET", "https://2130706433/api/x", "não canônica", "ipv4_decimal_encoding"),
    ("GET", "https://0x7f000001/api/x", "não canônica", "ipv4_hex_encoding"),
    ("GET", "https://0x7f.0.0.1/api/x", "não canônica", "ipv4_hex_octet"),
    ("GET", "https://0177.0.0.1/api/x", "não canônica", "ipv4_octal_encoding"),
    ("GET", "https://017700000001/api/x", "não canônica", "ipv4_octal_single_number"),
    ("GET", "https://127.1/api/x", "não canônica", "ipv4_short_form"),
    ("GET", "https://127.0.1/api/x", "não canônica", "ipv4_three_part_form"),
    ("GET", "https://localhost/api/x", "não está em scope.allow", "localhost_without_opt_in"),
    # porta e esquema
    ("GET", f"https://{HOST}:8443/api/x", "Esquema ou porta", "non_default_port"),
    ("GET", f"https://{HOST}:80/api/x", "Esquema ou porta", "http_port_with_https_scheme"),
    ("GET", f"http://{HOST}/api/x", "Esquema ou porta", "scheme_downgrade_to_http"),
    ("GET", f"http://{HOST}:443/api/x", "Esquema ou porta", "https_port_with_http_scheme"),
    ("GET", f"https://{HOST}:/api/x", "Porta", "empty_port"),
    ("GET", f"https://{HOST}:0443/api/x", "Porta", "port_with_leading_zero"),
    ("GET", f"https://{HOST}:443:443/api/x", "Porta", "double_port"),
    ("GET", f"ftp://{HOST}/api/x", "Esquema", "ftp_scheme"),
    ("GET", "file:///etc/passwd", "Esquema", "file_scheme"),
    ("GET", "javascript:alert(1)", "absoluta", "javascript_scheme"),
    ("GET", f"//{HOST}/api/x", "absoluta", "scheme_relative_url"),
    ("GET", "/api/x", "absoluta", "path_only_url"),
    ("GET", "api.permitido.com/api/x", "absoluta", "url_without_scheme"),
    ("GET", "https:///api/x", "Host ausente", "missing_host"),
    ("GET", "", "ausente", "empty_url"),
    # host: IDN e parecidos
    (
        "GET",
        "https://\u0430pi.permitido.com/api/x",
        "não está em scope.allow",
        "cyrillic_a_lookalike",
    ),
    (
        "GET",
        "https://xn--pi-6kc.permitido.com/api/x",
        "não está em scope.allow",
        "punycode_of_lookalike",
    ),
    ("GET", "https://xn--zz.permitido.com/api/x", "IDNA", "invalid_punycode"),
    ("GET", "https://api.permitido.com\u3002evil.com/api/x", "canônica", "ideographic_dot"),
    ("GET", "https://\uff41pi.permitido.com/api/x", "canônica", "fullwidth_letter"),
    ("GET", "https://api.permitido.com../api/x", "IDNA", "two_trailing_dots"),
    ("GET", f"https://{HOST}\u200b/api/x", "controle", "zero_width_space_in_host"),
    # caminho
    ("GET", f"{BASE}/api/../admin/x", "travessia", "dotdot_segment"),
    ("GET", f"{BASE}/api/./x", "travessia", "dot_segment"),
    ("GET", f"{BASE}/api/%2e%2e/etc", "travessia", "encoded_dotdot"),
    ("GET", f"{BASE}/api/%2E%2E/etc", "travessia", "encoded_dotdot_upper"),
    ("GET", f"{BASE}/api/.%2e/etc", "travessia", "half_encoded_dotdot"),
    ("GET", f"{BASE}/api/%252e%252e/etc", "dupla", "double_encoded_dotdot"),
    ("GET", f"{BASE}/api/%25252e/etc", "dupla", "triple_encoded_dot"),
    ("GET", f"{BASE}/api/..%2fadmin", "barra", "encoded_slash_after_dotdot"),
    ("GET", f"{BASE}/api%2f..%2fadmin", "barra", "encoded_slash_in_first_segment"),
    ("GET", f"{BASE}/api/a%5cb", "barra", "encoded_backslash"),
    ("GET", f"{BASE}/api\\..\\admin", "controle", "raw_backslash"),
    ("GET", f"{BASE}/api/..;/admin", "travessia", "dotdot_with_matrix_parameter"),
    ("GET", f"{BASE}//api/x", "vazio", "leading_double_slash"),
    ("GET", f"{BASE}/api//x", "vazio", "inner_double_slash"),
    ("GET", f"{BASE}/api/x%00.json", "barra", "encoded_nul"),
    ("GET", f"{BASE}/api/x%0d%0aHost:evil", "barra", "encoded_crlf"),
    ("GET", f"{BASE}/api/x\r\nHost: evil", "controle", "raw_crlf"),
    ("GET", f"{BASE}/api/a b", "controle", "raw_space"),
    ("GET", f"{BASE}/api/a\tb", "controle", "raw_tab"),
    ("GET", f"{BASE}/api/a\u202eb", "controle", "bidi_override"),
    ("GET", f"{BASE}/api/%ff", "UTF-8", "invalid_utf8_escape"),
    ("GET", f"{BASE}/api/%zz", "malformada", "bad_escape"),
    ("GET", f"{BASE}/api/café", "ASCII", "raw_non_ascii_path"),
    ("GET", f"{BASE}/apix", "não está coberto", "sibling_prefix_of_allowed_path"),
    ("GET", f"{BASE}/", "não está coberto", "root_path"),
    ("GET", f"{BASE}/outra/coisa", "não está coberto", "path_outside_allow"),
    ("GET", f"{BASE}/API/users", "não está coberto", "allow_is_case_sensitive"),
    # negação
    ("GET", f"{BASE}/api/admin", "deny_paths", "deny_matches_base_of_double_star"),
    ("GET", f"{BASE}/api/admin/users", "deny_paths", "deny_matches_child"),
    ("POST", f"{BASE}/api/admin/users/9/x", "deny_paths", "deny_matches_deep_child"),
    ("GET", f"{BASE}/api/ADMIN/users", "deny_paths", "deny_ignores_case"),
    ("GET", f"{BASE}/api/Conta/EXCLUIR", "deny_paths", "deny_exact_ignores_case"),
    ("GET", f"{BASE}/api/conta/excluir/", "deny_paths", "deny_with_trailing_slash"),
    ("GET", f"{BASE}/api/%61dmin/users", "deny_paths", "deny_after_percent_decoding"),
    ("GET", f"{BASE}/api/%EF%BC%A1dmin/users", "deny_paths", "deny_after_compatibility_folding"),
    ("GET", f"{BASE}/api/conta/excluir?x=1", "deny_paths", "deny_with_query"),
    # método
    ("DELETE", f"{BASE}/api/users", "método DELETE", "method_not_in_rule"),
    ("PUT", f"{BASE}/api/users", "método PUT", "put_not_in_rule"),
    ("get", f"{BASE}/api/users", "Método", "lowercase_method"),
    ("TRACE", f"{BASE}/api/users", "Método", "trace_method"),
    ("CONNECT", f"{HOST}:443", "Método", "connect_method"),
    ("", f"{BASE}/api/users", "Método", "empty_method"),
]


@pytest.mark.parametrize(
    ("method", "url", "fragment"),
    [pytest.param(m, u, f, id=i) for m, u, f, i in BYPASS_CASES],
)
def test_guard_rejects_request_when_it_is_a_known_bypass(
    method: str, url: str, fragment: str
) -> None:
    guard = make_guard()

    with pytest.raises(ScopeViolation, match=fragment) as caught:
        check(guard, method, url)

    assert caught.value.hint


def test_guard_rejects_method_when_only_another_rule_for_the_same_host_allows_it() -> None:
    guard = make_guard(
        make_rule(paths=["/api/leitura/**"], methods=["GET"]),
        make_rule(paths=["/api/escrita/**"], methods=["POST"]),
    )

    with pytest.raises(ScopeViolation, match="método POST"):
        check(guard, "POST", f"{BASE}/api/leitura/x")


def test_guard_rejects_when_a_rule_for_another_host_allows_the_path() -> None:
    guard = make_guard(make_rule(), make_rule(host="outro.permitido.com", paths=["/v2/**"]))

    with pytest.raises(ScopeViolation, match="não está coberto"):
        check(guard, "GET", f"{BASE}/v2/x")


def test_guard_denies_on_any_host_when_deny_path_is_global() -> None:
    guard = make_guard(make_rule(), make_rule(host="outro.permitido.com", paths=["/**"]))

    with pytest.raises(ScopeViolation, match="deny_paths"):
        check(guard, "GET", "https://outro.permitido.com/api/admin/x")


def test_guard_gives_deny_precedence_when_allow_rule_also_matches() -> None:
    guard = make_guard(make_rule(paths=["/**"], methods=["GET"]), deny=("/secreto/**",))

    with pytest.raises(ScopeViolation, match="deny_paths"):
        check(guard, "GET", f"{BASE}/secreto/x")


def test_guard_does_not_echo_url_secrets_when_request_is_rejected() -> None:
    guard = make_guard()

    with pytest.raises(ScopeViolation) as caught:
        check(guard, "GET", "https://outro.com/api/x?token=SEGREDO123")

    assert "SEGREDO123" not in caught.value.message
    assert "SEGREDO123" not in (caught.value.hint or "")


def test_guard_fails_closed_when_scope_has_a_single_rule_and_host_differs_by_one_char() -> None:
    with pytest.raises(ScopeViolation):
        check(make_guard(), "GET", "https://api.permitido.co/api/x")


# --------------------------------------------------------------- porta e esquema


def test_guard_allows_explicit_port_when_rule_declares_it() -> None:
    guard = make_guard(make_rule(port=8443))

    check(guard, "GET", f"{BASE}:8443/api/x")


def test_guard_rejects_default_port_when_rule_declares_a_different_one() -> None:
    guard = make_guard(make_rule(port=8443))

    with pytest.raises(ScopeViolation, match="Esquema ou porta"):
        check(guard, "GET", f"{BASE}/api/x")


def test_guard_allows_http_when_rule_declares_http_scheme() -> None:
    guard = make_guard(make_rule(scheme="http"))

    check(guard, "GET", f"http://{HOST}/api/x")


def test_guard_rejects_https_when_rule_declares_http_scheme() -> None:
    guard = make_guard(make_rule(scheme="http"))

    with pytest.raises(ScopeViolation, match="Esquema ou porta"):
        check(guard, "GET", f"{BASE}/api/x")


# ---------------------------------------------------------------------- laboratório


def lab_guard() -> ScopeGuard:
    rules = (
        make_rule(host="vampi", scheme="http", port=5000, allow_local=True, paths=["/**"]),
        make_rule(host="127.0.0.1", scheme="http", port=5000, allow_local=True, paths=["/**"]),
        make_rule(host="[::1]", scheme="http", port=5000, allow_local=True, paths=["/**"]),
    )
    return make_guard(*rules, deny=())


@pytest.mark.parametrize(
    "url",
    [
        "http://vampi:5000/users/v1",
        "http://VAMPI:5000/users/v1",
        "http://127.0.0.1:5000/users/v1",
        "http://[::1]:5000/users/v1",
        "http://[0:0:0:0:0:0:0:1]:5000/users/v1",
    ],
)
def test_guard_allows_lab_address_when_rule_opts_into_local(url: str) -> None:
    check(lab_guard(), "GET", url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.2:5000/x",
        "http://127.0.0.1:5001/x",
        "http://2130706433:5000/x",
        "http://0x7f000001:5000/x",
        "http://127.1:5000/x",
        "http://[::ffff:127.0.0.1]:5000/x",
        "http://169.254.169.254:5000/x",
        "http://vampi.evil.com:5000/x",
        "http://localhost:5000/x",
    ],
)
def test_guard_rejects_address_when_lab_rule_does_not_cover_it(url: str) -> None:
    with pytest.raises(ScopeViolation):
        check(lab_guard(), "GET", url)


# ------------------------------------------------------------------- IDN


def test_guard_treats_unicode_and_punycode_as_the_same_host_when_rule_is_idn() -> None:
    guard = make_guard(make_rule(host="münchen.example"))

    check(guard, "GET", "https://xn--mnchen-3ya.example/api/x")
    check(guard, "GET", "https://MÜNCHEN.example/api/x")
    check(guard, "GET", "https://münchen.example./api/x")


# ---------------------------------------------------------------- redirecionamento


def redirect(guard: ScopeGuard, location: str, method: str = "GET") -> None:
    guard.ensure_redirect_allowed(
        request=OutboundRequest(method="GET", url=f"{BASE}/api/start"),
        location=location,
        method=method,
    )


@pytest.mark.parametrize(
    "location",
    [
        pytest.param("/api/next", id="path_absolute"),
        pytest.param(f"{BASE}/api/next", id="absolute_same_host"),
        pytest.param(f"//{HOST}/api/next", id="scheme_relative_same_host"),
    ],
)
def test_guard_allows_redirect_when_target_is_in_scope(location: str) -> None:
    redirect(make_guard(), location)


@pytest.mark.parametrize(
    ("location", "fragment"),
    [
        pytest.param("https://outro.com/api/next", "não está em scope.allow", id="other_host"),
        pytest.param("//outro.com/api/next", "não está em scope.allow", id="scheme_relative_other"),
        pytest.param("http://api.permitido.com/api/next", "Esquema ou porta", id="downgrade"),
        pytest.param(f"{BASE}:8443/api/next", "Esquema ou porta", id="other_port"),
        pytest.param("/api/admin/x", "deny_paths", id="denied_path"),
        pytest.param("/outra", "não está coberto", id="path_outside_allow"),
        pytest.param("/api/../admin", "travessia", id="traversal"),
        pytest.param("next", "absoluta", id="relative_without_slash"),
        pytest.param("../next", "absoluta", id="relative_dotdot"),
        pytest.param("", "ausente", id="empty_location"),
        pytest.param("http://169.254.169.254/latest", "metadados", id="metadata"),
        pytest.param(f"https://{HOST}@outro.com/x", "Credenciais", id="userinfo"),
        pytest.param("///outro.com/api/x", "Host ausente", id="triple_slash"),
        pytest.param("/\\outro.com/api/x", "controle", id="slash_backslash"),
        pytest.param("/api/x\r\nX: y", "controle", id="header_injection"),
    ],
)
def test_guard_rejects_redirect_when_target_leaves_scope(location: str, fragment: str) -> None:
    with pytest.raises(ScopeViolation, match=fragment):
        redirect(make_guard(), location)


def test_guard_checks_redirect_with_the_method_the_client_will_use() -> None:
    with pytest.raises(ScopeViolation, match="método DELETE"):
        redirect(make_guard(), "/api/next", method="DELETE")


def test_guard_rejects_redirect_when_original_url_is_invalid() -> None:
    with pytest.raises(ScopeViolation):
        make_guard().ensure_redirect_allowed(
            request=OutboundRequest(method="GET", url="nao-e-url"),
            location="/api/x",
            method="GET",
        )


# ------------------------------------------------------------------ origem


def test_guard_accepts_origin_when_host_scheme_and_port_are_covered() -> None:
    make_guard().ensure_origin_allowed(f"{BASE}/qualquer/coisa")


@pytest.mark.parametrize("url", ["https://outro.com", f"http://{HOST}", f"{BASE}:8443"])
def test_guard_rejects_origin_when_any_part_is_not_covered(url: str) -> None:
    with pytest.raises(ScopeViolation):
        make_guard().ensure_origin_allowed(url)


# ------------------------------------------------------ OutboundRequest


def test_outbound_request_rejects_non_string_fields_and_extras() -> None:
    with pytest.raises(ValidationError):
        OutboundRequest(method="GET", url=123)  # type: ignore[arg-type]  # entrada inválida de propósito
    with pytest.raises(ValidationError):
        OutboundRequest(method="GET", url="https://a.com", body="x")  # type: ignore[call-arg]  # idem


# ------------------------------------------------------------------ propriedades

_ALLOWED_HOSTS = ["api.permitido.com", "API.PERMITIDO.COM", "api.permitido.com."]
_OTHER_HOSTS = [
    "outro.com",
    "api.permitido.com.evil.com",
    "evil.com@api.permitido.com",
    "api.permitido.com@evil.com",
    "127.0.0.1",
    "[::1]",
    "2130706433",
    "169.254.169.254",
    "xn--pi-6kc.permitido.com",
    "api.permitido.com:8443",
    "api.permitido.com:443",
    "",
]
_PATH_PIECES = [
    "api",
    "admin",
    "ADMIN",
    "conta",
    "excluir",
    "x",
    "..",
    ".",
    "%2e%2e",
    "%2E",
    "%252e",
    "a%2fb",
    "%61pi",
    "%61dmin",
    "",
    "users",
    "a;b",
    "..;",
]


@st.composite
def generated_requests(draw: st.DrawFn) -> tuple[str, str, str]:
    host = draw(
        st.one_of(
            st.sampled_from(_ALLOWED_HOSTS),
            st.sampled_from(_OTHER_HOSTS),
            st.text(alphabet="abcpermtido.-@:[]0123456789", max_size=20),
        )
    )
    pieces = draw(st.lists(st.sampled_from(_PATH_PIECES), max_size=6))
    scheme = draw(st.sampled_from(["https", "https", "http", "HTTPS", "ftp"]))
    method = draw(st.sampled_from(["GET", "POST", "PUT", "DELETE", "get", "TRACE"]))
    return method, f"{scheme}://{host}/" + "/".join(pieces), scheme


def _is_accepted(guard: ScopeGuard, method: str, url: str) -> bool:
    try:
        check(guard, method, url)
    except ScopeViolation:
        return False
    return True


def _oracle_covered(method: str, url: str) -> bool:
    """Condições NECESSÁRIAS para o escopo padrão do teste aceitar (oráculo independente)."""
    scheme, _, rest = url.partition("://")
    authority, _, path = rest.partition("/")
    host_ok = authority.lower().removesuffix(".") in {"api.permitido.com", "api.permitido.com:443"}
    pieces = [unquote(p) for p in path.split("/")]
    if pieces and pieces[-1] == "":
        pieces.pop()
    clean = all(
        p and p.split(";", 1)[0] not in {".", ".."} and not set(p) & set("/\\%") for p in pieces
    )
    return (
        scheme.lower() == "https"
        and host_ok
        and method in {"GET", "POST"}
        and bool(pieces)
        and pieces[0] == "api"
        and clean
    )


@settings(max_examples=600, deadline=None)
@given(request=generated_requests())
def test_guard_never_accepts_request_when_no_allow_rule_covers_it(
    request: tuple[str, str, str],
) -> None:
    method, url, _ = request

    accepted = _is_accepted(make_guard(), method, url)

    assert not accepted or _oracle_covered(method, url)


@settings(max_examples=600, deadline=None)
@given(request=generated_requests())
@example(request=("GET", "https://api.permitido.com/api/conta/excluir/api", "https"))
@example(request=("GET", "https://api.permitido.com/api/conta/excluir", "https"))
@example(request=("GET", "https://api.permitido.com/api/CONTA/EXCLUIR/", "https"))
def test_guard_never_accepts_request_when_a_deny_path_matches(
    request: tuple[str, str, str],
) -> None:
    method, url, _ = request
    if not _is_accepted(make_guard(), method, url):
        return

    segments = [unquote(p).casefold() for p in url.partition("://")[2].split("/")[1:] if p]

    assert not (len(segments) >= 2 and segments[1] == "admin")
    assert segments != ["api", "conta", "excluir"]


@pytest.mark.parametrize(
    ("path", "accepted"),
    [
        ("/api/conta/excluir", False),
        ("/api/conta/excluir/", False),
        ("/api/CONTA/EXCLUIR", False),
        ("/api/CONTA/EXCLUIR/", False),
        ("/api/conta/excluir/api", True),
        ("/api/CONTA/EXCLUIR/api/", True),
        ("/api/admin", False),
        ("/api/ADMIN/x", False),
    ],
)
def test_guard_applies_literal_and_recursive_deny_paths(path: str, accepted: bool) -> None:
    assert _is_accepted(make_guard(), "GET", f"{BASE}{path}") is accepted


def _mix_case(text: str, flags: list[bool]) -> str:
    return "".join(c.upper() if flag else c.lower() for c, flag in zip(text, flags, strict=False))


@settings(max_examples=300, deadline=None)
@given(
    flags=st.lists(st.booleans(), min_size=len(HOST), max_size=len(HOST)),
    dot=st.booleans(),
    path=st.sampled_from(["/api/x", "/api/admin/x", "/outra", "/api/../x"]),
    method=st.sampled_from(["GET", "POST", "DELETE"]),
)
def test_decision_is_invariant_when_host_changes_case_or_gets_trailing_dot(
    flags: list[bool], dot: bool, path: str, method: str
) -> None:
    guard = make_guard()
    variant = _mix_case(HOST, flags) + ("." if dot else "")

    reference = _is_accepted(guard, method, f"https://{HOST}{path}")
    varied = _is_accepted(guard, method, f"https://{variant}{path}")

    assert varied is reference


@settings(max_examples=300, deadline=None)
@given(text=st.text(max_size=60))
def test_guard_only_raises_scope_violation_when_url_is_arbitrary_text(text: str) -> None:
    try:
        check(make_guard(), "GET", text)
    except ScopeViolation:
        return


def test_guard_is_reusable_when_called_many_times() -> None:
    instance = make_guard()
    check(instance, "GET", f"{BASE}/api/x")

    with pytest.raises(ScopeViolation):
        check(instance, "GET", "https://outro.com/api/x")

    check(instance, "GET", f"{BASE}/api/y")
