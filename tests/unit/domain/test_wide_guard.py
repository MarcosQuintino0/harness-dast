"""`domain.wide_guard` e `domain.widepath`: o modo amplo libera mais e nega com paranoia."""

import unicodedata
from collections.abc import Callable
from urllib.parse import unquote

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.pathpattern import matches, parse_pattern
from harness_dast.domain.scope import OutboundRequest, Scope, ScopeGuard, ScopeRule
from harness_dast.domain.scope_reason import ScopeReason
from harness_dast.domain.wide_guard import WideOutcome, WideScopeGuard
from harness_dast.domain.widepath import MAX_READINGS, interpretations, literal_segments

HOST = "api.permitido.com"
BASE = f"https://{HOST}"
DENY = ("/api/admin/**", "/api/conta/excluir")
SCOPE = Scope(
    allow=(ScopeRule(host=HOST, paths=("/api/**",), methods=("GET", "POST")),),
    deny_paths=DENY,
)
WIDE = WideScopeGuard(SCOPE)
STRICT = ScopeGuard(SCOPE)


def wide(url: str, method: str = "GET") -> WideOutcome:
    return WIDE.ensure_allowed(OutboundRequest(method=method, url=url))


def reason_of(url: str, method: str = "GET") -> ScopeReason | None:
    with pytest.raises(ScopeViolation) as caught:
        wide(url, method)
    return caught.value.reason


# ------------------------------------------------------------------ liberar


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/api/users;jsessionid=1", id="matrix_parameter"),
        pytest.param("/api/users.", id="trailing_dot"),
        pytest.param("/api/users%20", id="trailing_space"),
        pytest.param("/api/a%2fb", id="encoded_slash"),
        pytest.param("/api/a%5cb", id="encoded_backslash"),
        pytest.param("/api/%252e%252e/x", id="double_encoding"),
        pytest.param("/api//users", id="empty_segment"),
        pytest.param("/api/100%", id="loose_percent"),
        pytest.param("/api/x/..;/y", id="dotdot_with_parameter"),
    ],
)
def test_wide_guard_allows_ambiguous_forms_when_the_literal_path_is_covered(path: str) -> None:
    wide(f"{BASE}{path}")

    with pytest.raises(ScopeViolation):
        STRICT.ensure_allowed(OutboundRequest(method="GET", url=f"{BASE}{path}"))


def test_wide_guard_accepts_what_strict_accepts_with_the_same_outcome() -> None:
    assert wide(f"{BASE}/api/users?token=x#frag") == WideOutcome(leaves_allow=False)


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("GET", f"{BASE}/fora", ScopeReason.PATH_NOT_ALLOWED),
        ("GET", f"{BASE}/api%2fusers", ScopeReason.PATH_NOT_ALLOWED),
        ("DELETE", f"{BASE}/api/users", ScopeReason.METHOD_NOT_ALLOWED),
        ("GET", "https://outro.com/api/users", ScopeReason.HOST_NOT_ALLOWED),
        ("GET", f"http://{HOST}/api/users", ScopeReason.ORIGIN_NOT_ALLOWED),
        ("GET", f"https://{HOST}:8443/api/users", ScopeReason.ORIGIN_NOT_ALLOWED),
    ],
)
def test_wide_guard_still_decides_scope_on_the_literal_reading(
    method: str, url: str, reason: ScopeReason
) -> None:
    assert reason_of(url, method) is reason


def test_wide_guard_wildcard_in_allow_does_not_match_an_empty_segment() -> None:
    guard = WideScopeGuard(
        Scope(allow=(ScopeRule(host=HOST, paths=("/api/*/x",), methods=("GET",)),))
    )

    with pytest.raises(ScopeViolation):
        guard.ensure_allowed(OutboundRequest(method="GET", url=f"{BASE}/api//x"))


# ------------------------------------------------- o que continua recusado


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        pytest.param("/api/x/./y", ScopeReason.PATH_DOT_SEGMENT, id="dot"),
        pytest.param("/api/x/../y", ScopeReason.PATH_DOT_SEGMENT, id="dotdot"),
        pytest.param("/api/x/%2e%2e/y", ScopeReason.PATH_DOT_SEGMENT, id="encoded_dotdot"),
        pytest.param("/api/x/%2E/y", ScopeReason.PATH_DOT_SEGMENT, id="encoded_dot"),
        pytest.param("/api/x%00", ScopeReason.PATH_CONTROL_CHAR, id="nul"),
        pytest.param("/api/x%0d%0a", ScopeReason.PATH_CONTROL_CHAR, id="crlf"),
        pytest.param("/api/x%e2%80%ae", ScopeReason.PATH_CONTROL_CHAR, id="bidi"),
        pytest.param("/api/%ff", ScopeReason.PATH_INVALID_UTF8, id="invalid_utf8"),
        pytest.param("/api/café", ScopeReason.URL_NOT_ASCII, id="raw_non_ascii"),
        pytest.param("/api\\x", ScopeReason.URL_FORBIDDEN_CHAR, id="raw_backslash"),
        pytest.param("/api/a b", ScopeReason.URL_FORBIDDEN_CHAR, id="raw_space"),
    ],
)
def test_wide_guard_keeps_refusing_literal_traversal_control_and_bad_bytes(
    path: str, reason: ScopeReason
) -> None:
    assert reason_of(f"{BASE}{path}") is reason


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("get", f"{BASE}/api/users", ScopeReason.METHOD_UNKNOWN),
        ("TRACE", f"{BASE}/api/users", ScopeReason.METHOD_UNKNOWN),
        ("GET", f"https://user@{HOST}/api/users", ScopeReason.CREDENTIALS_IN_URL),
        ("GET", f"ftp://{HOST}/api/users", ScopeReason.SCHEME_NOT_ALLOWED),
        ("GET", f"https://{HOST}:0080/api/users", ScopeReason.PORT_INVALID),
        ("GET", "https://169.254.169.254/api/users", ScopeReason.HOST_INVALID),
        ("GET", "/api/users", ScopeReason.URL_NOT_ABSOLUTE),
        ("GET", "", ScopeReason.URL_MISSING),
        ("GET", f"{BASE}/api/" + "a" * 2100, ScopeReason.URL_TOO_LONG),
    ],
)
def test_wide_guard_keeps_host_port_scheme_method_and_size_strict(
    method: str, url: str, reason: ScopeReason
) -> None:
    assert reason_of(url, method) is reason


# ------------------------------------------- tentativas de alcançar deny_paths

DENY_ATTEMPTS = [
    pytest.param("/api/x/..;/admin", id="dotdot_semicolon"),
    pytest.param("/api/x/..;/admin/y", id="dotdot_semicolon_child"),
    pytest.param("/api/x/%2e%2e;/admin", id="encoded_dotdot_semicolon"),
    pytest.param("/api/x/%252e%252e/admin", id="double_encoded_dotdot"),
    pytest.param("/api/x/%252e%252e%252fadmin", id="double_encoded_dotdot_slash"),
    pytest.param("/api/x/.;x/../admin", id="dot_semicolon_then_literal_dotdot"),
    pytest.param("/api/x/.;x/..;/admin", id="dot_semicolon_dotdot_semicolon"),
    pytest.param("/api/x%2f..%2fadmin", id="encoded_slash_traversal"),
    pytest.param("/api/x%2F..%2Fadmin", id="encoded_slash_upper"),
    pytest.param("/api/x%5c..%5cadmin", id="encoded_backslash_traversal"),
    pytest.param("/api/x/;x/../admin", id="semicolon_segment_then_dotdot"),
    pytest.param("/api//admin", id="double_slash"),
    pytest.param("/api///admin///x", id="triple_slash"),
    pytest.param("/api/ADMIN", id="uppercase"),
    pytest.param("/api/AdMiN/x", id="mixed_case"),
    pytest.param("/api/%EF%BC%A1dmin", id="fullwidth_letter"),
    pytest.param("/api%EF%BC%8Fadmin", id="fullwidth_solidus"),
    pytest.param("/api/x/%EF%BC%8E%EF%BC%8E/admin", id="fullwidth_dotdot"),
    pytest.param("/api/admin.json", id="format_suffix"),
    pytest.param("/api/admin.tar.gz", id="double_format_suffix"),
    pytest.param("/api/admin;x=1.json", id="param_then_suffix"),
    pytest.param("/api/admin.json;x=1", id="suffix_then_param"),
    pytest.param("/api/admin/", id="trailing_slash"),
    pytest.param("/api/admin%20", id="trailing_space"),
    pytest.param("/api/admin.", id="trailing_dot"),
    pytest.param("/api/admin. ", id="trailing_dot_space_raw_space_refused_anyway"),
    pytest.param("/api/admin%20.", id="trailing_space_dot"),
    pytest.param("/api/admin%2e", id="encoded_trailing_dot"),
    pytest.param("/api/admin;", id="empty_parameter"),
    pytest.param("/api/admin;x/y", id="parameter_on_segment"),
    pytest.param("/api/adm%69n", id="encoded_letter"),
    pytest.param("/api/adm%2569n", id="double_encoded_letter"),
    pytest.param("/api/adm%252569n", id="triple_encoded_letter"),
    pytest.param("/api/%2561dmin%2f", id="double_encoded_letter_and_slash"),
    pytest.param("/api/x/..%2fadmin", id="dotdot_encoded_slash"),
    pytest.param("/api/conta/excluir", id="plain_exact_deny"),
    pytest.param("/api/CONTA/Excluir.json", id="exact_deny_case_and_suffix"),
    pytest.param("/api/conta;x/excluir", id="parameter_in_the_middle"),
    pytest.param("/api/conta%2fexcluir", id="encoded_slash_in_exact_deny"),
    pytest.param("/api/x%2f%2e%2e%2fconta%2fexcluir", id="encoded_traversal_to_exact_deny"),
    pytest.param("/api/ADMIN%20;x.json", id="combination_case_space_param_suffix"),
    pytest.param("/api//ADMIN;x//", id="combination_slashes_case_param"),
    pytest.param("/api/x%252f..%252fadmin", id="double_encoded_slash_traversal"),
]


@pytest.mark.parametrize("path", DENY_ATTEMPTS)
def test_wide_guard_refuses_every_attempt_to_reach_a_denied_path(path: str) -> None:
    with pytest.raises(ScopeViolation) as caught:
        wide(f"{BASE}{path}")

    assert caught.value.reason in {
        ScopeReason.DENY_PATH,
        ScopeReason.URL_FORBIDDEN_CHAR,  # as grafias com espaço cru caem na regra de URL
        ScopeReason.PATH_DOT_SEGMENT,  # `.`/`..` literais nunca passam
    }


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/api/x/..;/admin", id="dotdot_semicolon"),
        pytest.param("/api/x%2f..%2fadmin", id="encoded_slash"),
        pytest.param("/api/ADMIN%20;x.json", id="combination"),
        pytest.param("/api/x%252f..%252fadmin", id="double_encoded"),
    ],
)
def test_wide_guard_names_deny_path_as_the_reason_for_the_core_attempts(path: str) -> None:
    assert reason_of(f"{BASE}{path}") is ScopeReason.DENY_PATH


def test_wide_guard_marks_a_release_whose_reading_leaves_allow() -> None:
    # `/api/..;/x` lido por um servidor vira `/x`, fora de `/api/**`, e não casa deny_paths.
    assert wide(f"{BASE}/api/%2e%2e;/interno") == WideOutcome(leaves_allow=True)


def test_wide_guard_does_not_mark_a_plain_release() -> None:
    assert wide(f"{BASE}/api/users/42") == WideOutcome(leaves_allow=False)


def test_wide_guard_denial_wins_over_a_host_outside_allow() -> None:
    assert reason_of("https://outro.com/api/admin;x") is ScopeReason.DENY_PATH


def test_wide_guard_refuses_a_path_with_too_many_readings() -> None:
    layers = "%" + "25" * 300 + "2e"
    assert reason_of(f"{BASE}/api/{layers}") is ScopeReason.PATH_TOO_MANY_READINGS


def test_wide_guard_origin_check_matches_the_strict_guard() -> None:
    WIDE.ensure_origin_allowed(f"{BASE}/")
    with pytest.raises(ScopeViolation):
        WIDE.ensure_origin_allowed("https://outro.com/")


# --------------------------------------------------------------- widepath


def test_literal_segments_decodes_once_and_keeps_encoded_slash_inside_the_segment() -> None:
    assert literal_segments("/a%2fb/c%252e/d;x/") == ("a/b", "c%2e", "d;x")


def test_literal_segments_of_the_root_is_empty() -> None:
    assert literal_segments("") == ()
    assert literal_segments("/") == ()


def test_interpretations_include_the_raw_path_and_the_resolved_reading() -> None:
    readings = interpretations("/a/%2e%2e;/b.json")

    assert ("a", "%2e%2e;", "b.json") in readings
    assert ("b",) in readings


def test_interpretations_are_bounded_and_deterministic() -> None:
    path = "/a%2fb;c/%2e%2e/d. /e.json//f"

    first = interpretations(path)

    assert first == interpretations(path)
    assert len(first) <= MAX_READINGS
    assert len(set(first)) == len(first)


def test_interpretations_of_an_empty_path_is_the_root() -> None:
    assert interpretations("") == ((),)


def test_trim_keeps_dotdot_as_traversal_instead_of_emptying_it() -> None:
    assert ("a",) in interpretations("/a/b/.. ")


# ----------------------------------------- propriedade com servidores-modelo
# Cada servidor-modelo é escrito aqui, sem reaproveitar `widepath`, com ordem própria de
# decodificar, remover `;`, aparar e resolver. Se algum deles levar o caminho a `deny_paths`, o
# guarda amplo TEM de recusar (por qualquer motivo).

_DENY_PATTERNS = tuple(parse_pattern(p) for p in DENY)


def _segments(path: str) -> list[str]:
    return path.split("/")[1:]


def _resolve(segments: list[str]) -> list[str]:
    out: list[str] = []
    for segment in segments:
        if segment == "..":
            if out:
                out.pop()
        elif segment != ".":
            out.append(segment)
    return out


def _strip_param(segment: str) -> str:
    return segment.split(";", 1)[0]


def _trim(segment: str) -> str:
    return segment if segment in {".", ".."} else segment.rstrip(". ")


def model_decode_param_resolve(path: str) -> list[str]:
    """Tomcat/Spring: decodifica, remove `;`, resolve, colapsa `//`."""
    decoded = unquote(path)
    return [s for s in _resolve([_strip_param(s) for s in _segments(decoded)]) if s]


def model_param_decode_trim_resolve(path: str) -> list[str]:
    """Remove `;` no cru, decodifica, apara, resolve."""
    stripped = "/".join(["", *(_strip_param(s) for s in _segments(path))])
    decoded = unquote(stripped)
    return _resolve([_trim(s) for s in _segments(decoded)])


def model_spring_suffix(path: str) -> list[str]:
    """Decodifica, remove `;`, resolve e tira o sufixo de formato do último segmento."""
    segments = _resolve([_strip_param(s) for s in _segments(unquote(path))])
    if segments and "." in segments[-1].strip("."):
        segments[-1] = segments[-1].rsplit(".", 1)[0]
    return segments


def model_iis_fixed_point(path: str) -> list[str]:
    """Decodifica até o ponto fixo, barra invertida vira barra, apara, resolve, ignora caixa."""
    current = path
    for _ in range(4):
        following = unquote(current)
        if following == current:
            break
        current = following
    current = current.replace("\\", "/")
    return _resolve([_trim(s) for s in _segments(current)])


def model_nfkc_after_decode(path: str) -> list[str]:
    """Decodifica, normaliza NFKC e só depois separa, remove `;` e resolve."""
    text = unicodedata.normalize("NFKC", unquote(path))
    return _resolve([_strip_param(s) for s in _segments(text)])


MODELS = (
    model_decode_param_resolve,
    model_param_decode_trim_resolve,
    model_spring_suffix,
    model_iis_fixed_point,
    model_nfkc_after_decode,
)

_PIECES = [
    "api", "admin", "ADMIN", "conta", "excluir", "x", "..", ".", "..;", ".;x", ";x", ";",
    "%2e%2e", "%2e", "%252e%252e", "%2f", "%2F", "%252f", "%5c", "%3b", "%20", "%2520",
    "admin.json", "admin.", "admin;x", "%61dmin", "%2561dmin", "%EF%BC%A1dmin",
    "", "a%2fb", "%EF%BC%8F", "%EF%BC%8E",
]  # fmt: skip


_paths = st.lists(st.sampled_from(_PIECES), min_size=1, max_size=7).map(
    lambda parts: "/api/" + "/".join(parts)
)


def _hits_deny(segments: list[str]) -> bool:
    return any(matches(pattern, tuple(segments), fold=True) for pattern in _DENY_PATTERNS)


@settings(max_examples=3000, deadline=None)
@given(_paths)
def test_wide_guard_refuses_any_path_that_a_model_server_routes_to_a_denied_path(
    path: str,
) -> None:
    hit_by = [m.__name__ for m in MODELS if _hits_deny(_safe(m, path))]
    if not hit_by:
        return

    with pytest.raises(ScopeViolation):
        wide(f"{BASE}{path}")


def _safe(model: Callable[[str], list[str]], path: str) -> list[str]:
    try:
        return model(path)
    except (ValueError, UnicodeError):
        return []


def test_model_servers_actually_reach_deny_paths_on_known_attempts() -> None:
    # Guarda contra uma propriedade vazia: os modelos precisam acertar a negação em tentativas
    # conhecidas, senão o teste acima não provaria nada.
    reaching = [
        "/api/x/..;/admin",
        "/api/x%2f..%2fadmin",
        "/api/admin.json",
        "/api/%252e%252e/api/admin",
        "/api/x/%5c..%5cadmin",
        "/api/%EF%BC%A1dmin",
    ]
    hits = {m.__name__ for path in reaching for m in MODELS if _hits_deny(_safe(m, path))}

    assert hits == {m.__name__ for m in MODELS}
