"""Testes independentes (QA) do ScopeGuard, escritos a partir da especificação."""

# ruff: noqa: S105, S104, S603, RUF001, RUF100, PT011, TRY301

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule


def make_guard(
    *,
    host: str = "allowed.com",
    paths: tuple[str, ...] = ("/api/**",),
    methods: tuple[str, ...] = ("GET", "POST"),
    deny: tuple[str, ...] = (),
    scheme: str = "https",
    port: int | None = None,
) -> ScopeGuard:
    rule = ScopeRule.model_validate(
        {"host": host, "paths": paths, "methods": methods, "scheme": scheme, "port": port}
    )
    return ScopeGuard(Scope(allow=(rule,), deny_paths=deny))


def allowed(guard: ScopeGuard, url: str, method: str = "GET") -> bool:
    try:
        guard.ensure_allowed(OutboundRequest(method=method, url=url))
    except ScopeViolation:
        return False
    return True


# ---------------------------------------------------------------- parser differentials
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com\\@allowed.com/api/x",
        "https://allowed.com\\@evil.com/api/x",
        "https://allowed.com:443@evil.com/api/x",
        "https://allowed.com@evil.com/api/x",
        "https://evil.com@allowed.com/api/x",
        "https://allowed.com%40evil.com/api/x",
        "https://allowed.com%2eevil.com/api/x",
        "https://allowed.com%00.evil.com/api/x",
        "https://evil.com/api/x",
        "https://allowed.com.evil.com/api/x",
        "https://evilallowed.com/api/x",
        "https://sub.allowed.com/api/x",
        "https://allowed.com:8443/api/x",
        "https://allowed.com:0/api/x",
        "https://allowed.com:65536/api/x",
        "https://allowed.com:/api/x",
        "https://allowed.com:+443/api/x",
        "https://allowed.com:4 43/api/x",
        "http://allowed.com/api/x",
        "https:/allowed.com/api/x",
        "https:allowed.com/api/x",
        "https:///allowed.com/api/x",
        "https:////allowed.com/api/x",
        "//allowed.com/api/x",
        "/api/x",
        "allowed.com/api/x",
        "ftp://allowed.com/api/x",
        "javascript://allowed.com/api/x",
        "file://allowed.com/api/x",
        "h\u0074tp s://allowed.com/api/x",
        " https://allowed.com/api/x",
        "https://allowed.com/api/x ",
        "https://allowed.com/api/x\n",
        "https://allowed.com/api/\tx",
        "https://allowed.com/api/x\r\nHost: evil.com",
        "https://allowed.com\n.evil.com/api/x",
        "https://allowed.com\t/api/x",
        "https://allowed.com\x00/api/x",
        "https://allowed.com/api/x\x00",
        "https://allowed.com/api/x\x7f",
        "https://[allowed.com]/api/x",
        "https://allowed.com]/api/x",
        "https://[allowed.com/api/x",
        "https://",
        "",
        "https://allowed.com..:443/api/x",
        "https://.allowed.com/api/x",
        "https://allowed..com/api/x",
        "https://allowed.com/" + "a" * 3000,
        "https://" + "a" * 64 + ".allowed.com/api/x",
        "https://" + "a" * 300 + ".com/api/x",
    ],
)
def test_ensure_allowed_denies_when_url_is_a_known_parser_differential(url: str) -> None:
    guard = make_guard()

    assert not allowed(guard, url)


@pytest.mark.parametrize(
    "url",
    [
        "https://allowed.com/api/x",
        "https://ALLOWED.COM/api/x",
        "https://allowed.com./api/x",
        "https://allowed.com:443/api/x",
        "HTTPS://allowed.com/api/x",
        "HtTpS://allowed.com/api/x",
        "https://allowed.com/api/x?q=1",
        "https://allowed.com/api/x#frag",
        "https://allowed.com/api/x?q=@evil.com",
        "https://allowed.com/api/x#@evil.com",
        "https://allowed.com/api/%78",
        "https://allowed.com/%61pi/x",
        "https://allowed.com/api/x/",
        "https://allowed.com/api",
    ],
)
def test_ensure_allowed_permits_when_url_is_a_legitimate_variant(url: str) -> None:
    guard = make_guard()

    assert allowed(guard, url)


@pytest.mark.parametrize(
    "url",
    [
        "https://allowed.com#@evil.com/api/x",
        "https://allowed.com?@evil.com",
    ],
)
def test_ensure_allowed_denies_when_authority_is_followed_by_fragment_or_query_only(
    url: str,
) -> None:
    # Sem caminho: nada em /api/**-> com a raiz '/', que não é coberta por /api/**.
    guard = make_guard()

    assert not allowed(guard, url)


def test_ensure_allowed_permits_when_only_origin_is_hit_and_root_is_allowed() -> None:
    guard = make_guard(paths=("/**",))

    assert allowed(guard, "https://allowed.com#@evil.com")
    assert allowed(guard, "https://allowed.com?@evil.com")


def test_ensure_allowed_denies_when_port_is_default_of_other_scheme() -> None:
    guard = make_guard()

    assert not allowed(guard, "http://allowed.com:443/api/x")
    assert not allowed(guard, "https://allowed.com:80/api/x")


def test_ensure_allowed_denies_when_port_is_written_with_leading_zeros() -> None:
    guard = make_guard(port=8443)

    assert allowed(guard, "https://allowed.com:8443/api/x")
    assert not allowed(guard, "https://allowed.com:08443/api/x")
    assert not allowed(guard, "https://allowed.com:0443/api/x")


def test_ensure_allowed_denies_when_rule_has_custom_port_and_url_has_default() -> None:
    guard = make_guard(port=8443)

    assert not allowed(guard, "https://allowed.com/api/x")
    assert not allowed(guard, "https://allowed.com:443/api/x")


def test_ensure_allowed_denies_when_rule_is_http_and_request_is_https() -> None:
    guard = make_guard(scheme="http")

    assert allowed(guard, "http://allowed.com/api/x")
    assert not allowed(guard, "https://allowed.com/api/x")


# ---------------------------------------------------------------- host look-alikes
@pytest.mark.parametrize(
    "host",
    [
        "аllowed.com",  # 'a' cirílico
        "allowed.cоm",  # 'o' cirílico
        "ａllowed.com",  # 'a' de largura total
        "allowed。com",  # ponto ideográfico
        "allowed．com",  # ponto de largura total
        "allowed｡com",  # ponto de meia largura
        "allowed.com\u200b",
        "al\u200blowed.com",
        "allowed.com\u00ad",
        "xn--allowed-.com",
        "xn--llowed-2nf.com",
        "xn--a.allowed.com",
        "allowed.com%25eth0",
        "ALLOWED.com%2e",
        "allowed_.com",
        "-allowed.com",
        "allowed-.com",
        "allowed.com..",
        "allowed.com...",
        "..allowed.com",
        "allowed .com",
        "allowed.com:",
        "ａ" * 3,
    ],
)
def test_ensure_allowed_denies_when_host_is_a_lookalike_or_malformed(host: str) -> None:
    guard = make_guard(paths=("/**",))

    assert not allowed(guard, f"https://{host}/x")


@pytest.mark.parametrize(
    "host",
    [
        "[::ffff:169.254.169.254]",
        "[::ffff:a9fe:a9fe]",
        "[0:0:0:0:0:ffff:a9fe:a9fe]",
        "[fe80::1%25eth0]",
        "[fe80::1%eth0]",
        "[::1%25lo]",
        "[::1",
        "::1",
        "[::1]]",
        "[[::1]]",
        "169.254.169.254",
        "169.254.169.254.",
        "0xa9.0xfe.0xa9.0xfe",
        "0xa9fea9fe",
        "2852039166",
        "0251.0376.0251.0376",
        "169.254.43518",
        "169.16689662",
        "metadata.google.internal",
        "metadata.google.internal.",
        "METADATA.GOOGLE.INTERNAL",
        "[fd00:ec2::254]",
        "0.0.0.0",
        "[::]",
        "224.0.0.1",
        "255.255.255.255",
    ],
)
def test_ensure_allowed_denies_when_host_is_a_metadata_or_ambiguous_address(host: str) -> None:
    guard = make_guard(paths=("/**",))

    assert not allowed(guard, f"https://{host}/x")
    assert not allowed(guard, f"http://{host}:80/x")


@pytest.mark.parametrize(
    "rule_host",
    ["169.254.169.254", "metadata.google.internal", "0.0.0.0", "[::ffff:169.254.169.254]"],
)
def test_scope_rule_rejects_metadata_hosts_even_with_allow_local(rule_host: str) -> None:
    with pytest.raises(ValueError, match=r"host|IP|metadados|proibid"):
        ScopeRule.model_validate(
            {"host": rule_host, "paths": ["/**"], "methods": ["GET"], "allow_local": True}
        )


# ---------------------------------------------------------------- paths
@pytest.mark.parametrize(
    "path",
    [
        "/apiv2/x",
        "/apix",
        "/API/x",
        "/Api",
        "/ap",
        "/",
        "/admin",
        "/api/../admin",
        "/api/./../admin",
        "/api/%2e%2e/admin",
        "/api/%2E%2E/admin",
        "/api/.%2e/admin",
        "/api/%252e%252e/admin",
        "/api/..%2fadmin",
        "/api/..%5cadmin",
        "/api/..\\admin",
        "/api/..;/admin",
        "/api/%2e%2e;/admin",
        "/api//x",
        "//api/x",
        "/api/%2fx",
        "/api/%2Fx",
        "/api/%5Cx",
        "/api/x%00",
        "/api/x%0a",
        "/api/x%0d%0aSet-Cookie:a=b",
        "/api/%c0%af",
        "/api/%c0%ae%c0%ae/admin",
        "/api/%e0%80%af",
        "/api/%",
        "/api/%zz",
        "/api/%4",
        "/api/%u002e",
        "/api/x%25",
        "/api/\u2215x",
        "/api/é",
    ],
)
def test_ensure_allowed_denies_when_path_escapes_or_is_not_covered(path: str) -> None:
    guard = make_guard()

    assert not allowed(guard, "https://allowed.com" + path)


@pytest.mark.parametrize(
    ("patterns", "path", "expected"),
    [
        (("/api/*",), "/api/a", True),
        (("/api/*",), "/api", False),
        (("/api/*",), "/api/a/b", False),
        (("/api/*",), "/api/", False),
        (("/api/**",), "/api", True),
        (("/api/**",), "/api/", True),
        (("/api/**",), "/api/a/b/c", True),
        (("/api/**",), "/api2", False),
        (("/api/**",), "/apiv2/a", False),
        (("/api/**/x",), "/api/x", True),
        (("/api/**/x",), "/api/a/b/x", True),
        (("/api/**/x",), "/api/a/b/y", False),
        (("/api/**/x",), "/api/x/y", False),
        (("/**",), "/", True),
        (("/**",), "/a/b", True),
        (("/",), "/", True),
        (("/",), "/a", False),
        (("/users/*/orders",), "/users/1/orders", True),
        (("/users/*/orders",), "/users/orders", False),
        (("/users/*/orders",), "/users/1/2/orders", False),
        (("/a", "/b"), "/b", True),
        (("/a", "/b"), "/c", False),
    ],
)
def test_ensure_allowed_follows_wildcard_semantics_when_patterns_use_star(
    patterns: tuple[str, ...], path: str, expected: bool
) -> None:
    guard = make_guard(paths=patterns)

    assert allowed(guard, "https://allowed.com" + path) is expected


# ---------------------------------------------------------------- deny precedence
def test_ensure_allowed_denies_when_deny_matches_even_if_allow_matches_exactly() -> None:
    guard = make_guard(paths=("/api/conta/excluir",), deny=("/api/conta/excluir",))

    assert not allowed(guard, "https://allowed.com/api/conta/excluir")


@pytest.mark.parametrize(
    "path",
    [
        "/admin",
        "/admin/",
        "/ADMIN",
        "/Admin/users",
        "/%61dmin",
        "/%41DMIN/x",
        "/admin/x/y/z",
        "/x/admin",
    ],
)
def test_ensure_allowed_denies_when_path_matches_deny_in_any_spelling(path: str) -> None:
    guard = make_guard(paths=("/**",), deny=("/admin", "/admin/**", "/**/admin"))

    assert not allowed(guard, "https://allowed.com" + path)


@pytest.mark.parametrize(
    "path",
    [
        "/admin;x=1",
        "/admin;jsessionid=abc",
        "/admin%3Bx=1",
        "/admin%20",
        "/admin.",
        "/admin..",
        "/admin%2e",
        "/admin/;x",
        "/admin;/x",
    ],
)
def test_ensure_allowed_denies_when_path_is_deny_target_with_server_side_decoration(
    path: str,
) -> None:
    # Servidores (Tomcat/Spring/IIS) removem ';param', espaço e ponto finais antes do
    # roteamento. Falhar fechado exige que a negação de /admin não seja contornável por eles.
    guard = make_guard(paths=("/**",), deny=("/admin", "/admin/**"))

    assert not allowed(guard, "https://allowed.com" + path)


def test_ensure_allowed_denies_when_deny_pattern_is_unicode_composed_differently() -> None:
    guard = make_guard(paths=("/**",), deny=("/caf\u00e9",))

    assert not allowed(guard, "https://allowed.com/cafe%CC%81")
    assert not allowed(guard, "https://allowed.com/caf%C3%A9")
    assert not allowed(guard, "https://allowed.com/CAF%C3%89")


def test_ensure_allowed_denies_when_deny_applies_to_any_host() -> None:
    rules = (
        ScopeRule(host="a.example.com", paths=("/**",), methods=("GET",)),
        ScopeRule(host="b.example.com", paths=("/**",), methods=("GET",)),
    )
    guard = ScopeGuard(Scope(allow=rules, deny_paths=("/secret/**",)))

    assert not allowed(guard, "https://a.example.com/secret/x")
    assert not allowed(guard, "https://b.example.com/secret")


def test_ensure_allowed_ignores_query_when_deciding_deny() -> None:
    guard = make_guard(paths=("/**",), deny=("/admin",))

    assert allowed(guard, "https://allowed.com/ok?next=/admin")
    assert not allowed(guard, "https://allowed.com/admin?x=1")


# ---------------------------------------------------------------- methods
@pytest.mark.parametrize(
    "method",
    [
        "get",
        "Get",
        "gET",
        "TRACE",
        "CONNECT",
        "PROPFIND",
        "",
        " GET",
        "GET ",
        "GET\n",
        "G\u0045T",
        "ＧＥＴ",
    ],
)
def test_ensure_allowed_denies_when_method_is_unknown_or_not_uppercase(method: str) -> None:
    guard = make_guard(methods=("GET",))

    # "G\u0045T" é literalmente "GET" e portanto permitido; o resto não.
    expected = method == "GET"
    assert allowed(guard, "https://allowed.com/api/x", method) is expected


def test_ensure_allowed_denies_when_method_is_known_but_not_in_rule() -> None:
    guard = make_guard(methods=("GET",))

    for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        assert not allowed(guard, "https://allowed.com/api/x", method)


def test_ensure_allowed_uses_methods_of_matching_path_rule_when_rules_overlap() -> None:
    rules = (
        ScopeRule(host="allowed.com", paths=("/a/**",), methods=("GET",)),
        ScopeRule(host="allowed.com", paths=("/b/**",), methods=("DELETE",)),
    )
    guard = ScopeGuard(Scope(allow=rules))

    assert allowed(guard, "https://allowed.com/a/x", "GET")
    assert not allowed(guard, "https://allowed.com/a/x", "DELETE")
    assert not allowed(guard, "https://allowed.com/b/x", "GET")
    assert allowed(guard, "https://allowed.com/b/x", "DELETE")


def test_scope_rule_rejects_when_method_is_lowercase_or_unknown() -> None:
    for methods in (["get"], ["TRACE"], ["CONNECT"], ["GET", "get"], [""]):
        with pytest.raises(ValueError, match="método"):
            ScopeRule.model_validate({"host": "allowed.com", "paths": ["/"], "methods": methods})


# ---------------------------------------------------------------- redirects
def _redirect(guard: ScopeGuard, location: str, method: str = "GET") -> bool:
    try:
        guard.ensure_redirect_allowed(
            request=OutboundRequest(method="GET", url="https://allowed.com/api/start"),
            location=location,
            method=method,
        )
    except ScopeViolation:
        return False
    return True


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.com/api/x",
        "http://allowed.com/api/x",
        "//evil.com/api/x",
        "///evil.com/api/x",
        "////evil.com/api/x",
        "/\\evil.com/api/x",
        "\\\\evil.com/api/x",
        "foo",
        "x/../../admin",
        "../admin",
        "./x",
        "?x=1",
        "#frag",
        "",
        " ",
        "https:evil.com",
        "https:/evil.com",
        "http:allowed.com/api/x",
        "javascript:alert(1)",
        "data:text/html,x",
        "/api/../admin",
        "/api/x\r\nX: y",
        "/admin",
        "https://allowed.com:8443/api/x",
        "https://allowed.com@evil.com/api/x",
        "//allowed.com@evil.com/api/x",
    ],
)
def test_ensure_redirect_allowed_denies_when_location_leaves_scope_or_is_ambiguous(
    location: str,
) -> None:
    guard = make_guard()

    assert not _redirect(guard, location)


@pytest.mark.parametrize(
    "location",
    ["/api/next", "https://allowed.com/api/next", "//allowed.com/api/next", "/api/next?x=1#f"],
)
def test_ensure_redirect_allowed_permits_when_location_stays_in_scope(location: str) -> None:
    guard = make_guard()

    assert _redirect(guard, location)


def test_ensure_redirect_allowed_denies_when_method_after_redirect_is_not_permitted() -> None:
    guard = make_guard(methods=("POST",))

    assert not _redirect(guard, "/api/next", method="GET")
    assert _redirect(guard, "/api/next", method="POST")


def test_ensure_redirect_allowed_denies_when_request_base_is_out_of_scope() -> None:
    guard = make_guard()

    with pytest.raises(ScopeViolation):
        guard.ensure_redirect_allowed(
            request=OutboundRequest(method="GET", url="https://evil.com/"),
            location="/api/x",
            method="GET",
        )


def test_ensure_redirect_allowed_denies_when_redirect_lands_on_deny_path() -> None:
    guard = make_guard(paths=("/**",), deny=("/admin",))

    assert not _redirect(guard, "/admin")
    assert not _redirect(guard, "/ADMIN/")


def test_ensure_allowed_keeps_scheme_and_port_pairs_apart_when_two_rules_share_host() -> None:
    rules = (
        ScopeRule(host="allowed.com", paths=("/**",), methods=("GET",)),
        ScopeRule(host="allowed.com", paths=("/**",), methods=("GET",), scheme="http", port=8080),
    )
    guard = ScopeGuard(Scope(allow=rules))

    assert not allowed(guard, "http://allowed.com/x")
    assert allowed(guard, "http://allowed.com:8080/x")
    assert not allowed(guard, "https://allowed.com:8080/x")


# ---------------------------------------------------------------- error messages
def test_ensure_allowed_error_does_not_echo_url_secrets() -> None:
    guard = make_guard()
    secret = "TOKEN-SUPERSECRETO-123"

    for url in (
        f"https://evil.com/api/x?token={secret}",
        f"https://user:{secret}@allowed.com/api/x",
        f"https://{secret}.evil.com/",
    ):
        with pytest.raises(ScopeViolation) as caught:
            guard.ensure_allowed(OutboundRequest(method="GET", url=url))
        assert secret not in caught.value.message
        assert secret not in (caught.value.hint or "")
        assert secret not in str(caught.value)


def test_ensure_allowed_error_does_not_echo_path_when_path_may_carry_a_token() -> None:
    # Contrato do docstring de ensure_allowed: "A mensagem não repete a URL (pode ter segredos)".
    guard = make_guard(paths=("/api/**",))
    secret = "RESET-TOKEN-SUPERSECRETO-123"

    with pytest.raises(ScopeViolation) as caught:
        guard.ensure_allowed(OutboundRequest(method="GET", url=f"https://allowed.com/{secret}"))

    assert secret not in caught.value.message


def test_ensure_allowed_raises_only_scope_violation_when_input_is_garbage() -> None:
    guard = make_guard()
    for url in ("\ud800", "https://\ud800.com/", "https://allowed.com/\udfff", "\x00" * 10):
        with pytest.raises(ScopeViolation):
            guard.ensure_allowed(OutboundRequest(method="GET", url=url))


def test_scope_guard_is_stateless_between_calls() -> None:
    guard = make_guard()

    first = allowed(guard, "https://allowed.com/api/x")
    allowed(guard, "https://evil.com/")
    second = allowed(guard, "https://allowed.com/api/x")

    assert first
    assert second


def test_ensure_origin_allowed_ignores_path_but_not_host_scheme_or_port() -> None:
    guard = make_guard(paths=("/only/here",))

    guard.ensure_origin_allowed("https://allowed.com/anything/else")
    for url in ("http://allowed.com/", "https://allowed.com:8443/", "https://other.com/"):
        with pytest.raises(ScopeViolation):
            guard.ensure_origin_allowed(url)


# ---------------------------------------------------------------- properties
_LABEL = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=8)
_WEIRD = st.text(
    alphabet=st.sampled_from(list("abc./:@\\?#%;[]\t\n ")) | st.characters(),
    min_size=0,
    max_size=30,
)


@settings(max_examples=300, deadline=None)
@given(prefix=st.sampled_from(["https://", "http://", "", "//"]), tail=_WEIRD)
def test_ensure_allowed_never_permits_other_host_when_text_is_arbitrary(
    prefix: str, tail: str
) -> None:
    # Oráculo independente: se a requisição foi permitida, um parser ingênuo e estrito
    # (RFC 3986 simplificado) tem de enxergar exatamente o host permitido.
    guard = make_guard(paths=("/**",), methods=("GET",))
    url = prefix + tail
    if not allowed(guard, url):
        return
    assert url.startswith("https://") or url.lower().startswith("https://")
    rest = url[len("https://") :]
    authority = rest.split("/")[0].split("?")[0].split("#")[0]
    assert "@" not in authority
    assert "\\" not in url
    assert authority.lower().rstrip(".") in ("allowed.com", "allowed.com:443")


@settings(max_examples=200, deadline=None)
@given(
    segments=st.lists(
        st.text(alphabet=st.sampled_from(list("ab.%;2eEfF5cC/\\ ")), min_size=0, max_size=6),
        max_size=5,
    )
)
def test_ensure_allowed_never_permits_traversal_when_segments_are_arbitrary(
    segments: list[str],
) -> None:
    guard = make_guard(paths=("/api/**",), methods=("GET",), deny=("/api/admin", "/api/admin/**"))
    url = "https://allowed.com/api/" + "/".join(segments)
    if not allowed(guard, url):
        return
    from urllib.parse import unquote

    decoded = unquote(url.split("://", 1)[1].split("?")[0].split("#")[0])
    parts = decoded.split("/")[1:]
    assert ".." not in parts
    assert "." not in [p.split(";")[0] for p in parts]
    assert [p.lower() for p in parts[:2]] != ["api", "admin"]
