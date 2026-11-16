# ruff: noqa: PT011, RUF007, S104
"""QA independente do motor do proxy de escopo (`adapters/scope_proxy`).

Escrito a partir dos docstrings: nenhuma requisição é liberada sem passar por trava/prazo,
recusa de upgrade, coerência do cabeçalho `Host`, `ScopeGuard` e endereço resolvido; a trava é
TRAVADA até reiniciar; o prazo é o menor entre `not_after` e início + duração; a taxa espaça os
pedidos e a fila é limitada; toda decisão gera uma linha de auditoria sem valores de consulta.
"""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness_dast.adapters.scope_proxy.addresses import check_addresses
from harness_dast.adapters.scope_proxy.decision import Reason, Verdict
from harness_dast.adapters.scope_proxy.engine import ScopeProxyEngine
from harness_dast.adapters.scope_proxy.policy import (
    KILL_FLAG_NAME,
    ProxyPolicy,
    deadline_of,
    parse_policy,
)
from harness_dast.adapters.scope_proxy.ratelimit import RateLimiter
from harness_dast.domain.errors import ConfigError

RUN_ID = "2026-11-13T10-00-00Z-demo-7f3a"
T0 = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
API = "https://api.example.com"


def policy_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "scope": {
            "allow": [
                {"host": "api.example.com", "paths": ["/v1/**"], "methods": ["GET", "POST"]},
                {
                    "host": "lab.internal",
                    "paths": ["/**"],
                    "methods": ["GET"],
                    "scheme": "http",
                    "port": 8080,
                    "allow_local": True,
                },
            ],
            "deny_paths": ["/v1/admin/**"],
        },
        "limits": {"requests_per_second": 5, "max_duration_minutes": 60, "zap_threads_per_host": 2},
        "not_after": (T0 + timedelta(hours=2)).isoformat(),
    }
    data.update(overrides)
    return data


def make_policy(**overrides: object) -> ProxyPolicy:
    return parse_policy(json.dumps(policy_data(**overrides)).encode())


class Clock:
    def __init__(self) -> None:
        self.value = T0
        self.mono = 1000.0

    def now(self) -> datetime:
        return self.value

    def monotonic(self) -> float:
        return self.mono


def make_engine(
    tmp_path: Path, clock: Clock | None = None, **overrides: object
) -> tuple[ScopeProxyEngine, Clock, io.StringIO]:
    clock = clock or Clock()
    audit = io.StringIO()
    engine = ScopeProxyEngine(
        make_policy(**overrides),
        policy_dir=tmp_path,
        audit_file=audit,
        stdout=io.StringIO(),
        now=clock.now,
        monotonic=clock.monotonic,
    )
    return engine, clock, audit


def check(engine: ScopeProxyEngine, method: str, url: str, host: str | None = None) -> Verdict:
    from urllib.parse import urlsplit

    return engine.check_request(
        method=method,
        url=url,
        host_header=host if host is not None else urlsplit(url).netloc,
        wants_upgrade=False,
    )


# ------------------------------------------------------------------ escopo por requisição


def test_check_request_allows_when_request_is_inside_the_scope(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)

    assert check(engine, "GET", f"{API}/v1/users").allowed


@pytest.mark.parametrize(
    ("method", "url", "reason"),
    [
        ("GET", "https://evil.example.org/v1/users", Reason.HOST_NOT_ALLOWED),
        ("GET", f"{API}/v1/admin/users", Reason.DENY_PATH),
        ("GET", f"{API}/V1/ADMIN/users", Reason.DENY_PATH),
        ("GET", f"{API}/v1/%61dmin/users", Reason.DENY_PATH),
        ("GET", f"{API}/v1/admin;x=1", Reason.MALFORMED_REQUEST),
        ("GET", f"{API}/v1/admin./x", Reason.MALFORMED_REQUEST),
        ("GET", f"{API}/v1/../v1/admin/x", Reason.MALFORMED_REQUEST),
        ("GET", f"{API}/v1/%2e%2e/admin", Reason.MALFORMED_REQUEST),
        ("GET", f"{API}//v1/users", Reason.MALFORMED_REQUEST),
        ("GET", f"{API}/other", Reason.PATH_NOT_ALLOWED),
        ("DELETE", f"{API}/v1/users/1", Reason.METHOD_NOT_ALLOWED),
        ("get", f"{API}/v1/users", Reason.MALFORMED_REQUEST),
        ("TRACE", f"{API}/v1/users", Reason.MALFORMED_REQUEST),
        ("GET", "http://api.example.com/v1/users", Reason.ORIGIN_NOT_ALLOWED),
        ("GET", "https://api.example.com:8443/v1/users", Reason.ORIGIN_NOT_ALLOWED),
        ("GET", "https://user@api.example.com/v1/users", Reason.MALFORMED_REQUEST),
        ("GET", "https://api.example.com.evil.org/v1/users", Reason.HOST_NOT_ALLOWED),
        ("GET", "https://169.254.169.254/latest/meta-data", Reason.MALFORMED_REQUEST),
        ("GET", "ftp://api.example.com/v1/users", Reason.MALFORMED_REQUEST),
        ("GET", "/v1/users", Reason.MALFORMED_REQUEST),
        ("GET", "", Reason.MALFORMED_REQUEST),
    ],
)
def test_check_request_denies_with_a_stable_reason_when_request_leaves_the_scope(
    tmp_path: Path, method: str, url: str, reason: Reason
) -> None:
    engine, _, _ = make_engine(tmp_path)

    verdict = check(engine, method, url, host="api.example.com")

    assert not verdict.allowed
    assert verdict.reason is reason


@pytest.mark.parametrize(
    "host_header",
    [
        None,
        "",
        "evil.example.org",
        "api.example.com.evil.org",
        "api.example.com:8443",
        "api.example.com, evil.example.org",
        "api.example.com@evil.org",
        "api.example.com/x",
        "api.example.com?x",
        "api.example.com#@evil.org",
        "api.example.com\\x",
    ],
)
def test_check_request_denies_when_host_header_disagrees_with_the_url(
    tmp_path: Path, host_header: str | None
) -> None:
    engine, _, _ = make_engine(tmp_path)

    verdict = engine.check_request(
        method="GET", url=f"{API}/v1/users", host_header=host_header, wants_upgrade=False
    )

    assert not verdict.allowed
    assert verdict.reason is Reason.HOST_HEADER_MISMATCH


@pytest.mark.parametrize(
    "host_header", ["api.example.com", "API.EXAMPLE.COM", "api.example.com:443"]
)
def test_check_request_allows_when_host_header_is_the_same_origin_in_another_spelling(
    tmp_path: Path, host_header: str
) -> None:
    engine, _, _ = make_engine(tmp_path)

    assert engine.check_request(
        method="GET", url=f"{API}/v1/users", host_header=host_header, wants_upgrade=False
    ).allowed


def test_check_request_denies_every_protocol_upgrade(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)

    verdict = engine.check_request(
        method="GET", url=f"{API}/v1/users", host_header="api.example.com", wants_upgrade=True
    )

    assert verdict.reason is Reason.UPGRADE_REFUSED


# --------------------------------------------------------------------------- CONNECT


@pytest.mark.parametrize(
    ("host", "port", "allowed"),
    [
        ("api.example.com", 443, True),
        ("API.example.com", 443, True),
        ("api.example.com", 8443, False),
        ("api.example.com", 80, False),
        ("evil.example.org", 443, False),
        ("api.example.com/x", 443, False),
        ("api.example.com?x", 443, False),
        ("api.example.com#x", 443, False),
        ("user@api.example.com", 443, False),
        ("api.example.com\\@evil.org", 443, False),
        ("api.example.com%2f", 443, False),
        ("api.example.com ", 443, False),
        ("", 443, False),
        ("lab.internal", 8080, False),
    ],
)
def test_check_connect_decides_by_host_and_port_only_for_https_tunnels(
    tmp_path: Path, host: str, port: int, allowed: bool
) -> None:
    engine, _, _ = make_engine(tmp_path)

    assert engine.check_connect(host, port).allowed is allowed


# ------------------------------------------------------------------ trava de emergência


def test_check_request_denies_everything_after_kill_file_appears(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)
    assert check(engine, "GET", f"{API}/v1/users").allowed

    (tmp_path / KILL_FLAG_NAME).touch()

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.KILL_SWITCH
    assert engine.check_connect("api.example.com", 443).reason is Reason.KILL_SWITCH


def test_check_request_stays_denied_when_kill_file_is_removed_afterwards(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)
    flag = tmp_path / KILL_FLAG_NAME
    flag.touch()
    assert not check(engine, "GET", f"{API}/v1/users").allowed

    flag.unlink()

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.KILL_SWITCH
    assert engine.check_connect("api.example.com", 443).reason is Reason.KILL_SWITCH
    assert engine.recheck_after_wait().reason is Reason.KILL_SWITCH


def test_check_request_denies_when_kill_file_exists_from_the_start(tmp_path: Path) -> None:
    (tmp_path / KILL_FLAG_NAME).touch()
    engine, _, _ = make_engine(tmp_path)

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.KILL_SWITCH


def test_recheck_after_wait_denies_when_kill_file_appears_during_the_wait(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)
    assert check(engine, "GET", f"{API}/v1/users").allowed
    assert engine.recheck_after_wait().allowed

    (tmp_path / KILL_FLAG_NAME).touch()

    assert engine.recheck_after_wait().reason is Reason.KILL_SWITCH


def test_check_request_denies_when_kill_flag_cannot_be_inspected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Não saber se a trava está acionada (erro de E/S ao consultar o arquivo) deve travar.
    engine, _, _ = make_engine(tmp_path)

    def denied(self: Path) -> bool:
        raise PermissionError("sem acesso")

    monkeypatch.setattr(Path, "lstat", denied)

    assert not check(engine, "GET", f"{API}/v1/users").allowed


# ------------------------------------------------------------------------------ prazo


def test_check_request_denies_when_the_max_duration_has_elapsed(tmp_path: Path) -> None:
    engine, clock, _ = make_engine(tmp_path)
    clock.value = T0 + timedelta(minutes=59, seconds=59)
    assert check(engine, "GET", f"{API}/v1/users").allowed

    clock.value = T0 + timedelta(minutes=60)

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.RUN_EXPIRED


def test_check_request_denies_at_not_after_when_it_comes_before_the_duration(
    tmp_path: Path,
) -> None:
    engine, clock, _ = make_engine(tmp_path, not_after=(T0 + timedelta(minutes=10)).isoformat())

    clock.value = T0 + timedelta(minutes=9, seconds=59)
    assert check(engine, "GET", f"{API}/v1/users").allowed
    clock.value = T0 + timedelta(minutes=10)

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.RUN_EXPIRED


def test_check_request_denies_everything_when_not_after_is_already_in_the_past(
    tmp_path: Path,
) -> None:
    engine, _, _ = make_engine(tmp_path, not_after=(T0 - timedelta(seconds=1)).isoformat())

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.RUN_EXPIRED


def test_check_request_stays_denied_when_the_clock_goes_backwards_after_expiry(
    tmp_path: Path,
) -> None:
    engine, clock, _ = make_engine(tmp_path)
    clock.value = T0 + timedelta(hours=3)
    assert not check(engine, "GET", f"{API}/v1/users").allowed

    clock.value = T0

    assert not check(engine, "GET", f"{API}/v1/users").allowed


def test_deadline_of_is_the_earlier_of_not_after_and_start_plus_duration() -> None:
    policy = make_policy()

    assert deadline_of(policy, T0) == T0 + timedelta(minutes=60)
    assert deadline_of(policy, T0 + timedelta(hours=1, minutes=30)) == T0 + timedelta(hours=2)


# --------------------------------------------------------------------------------- taxa


def test_reserve_slot_spaces_requests_by_the_inverse_of_the_rate(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)  # 5 req/s => 0,2 s

    delays = [engine.reserve_slot() for _ in range(4)]

    assert delays == pytest.approx([0.0, 0.2, 0.4, 0.6])


def test_reserve_slot_never_allows_a_burst_after_an_idle_period(tmp_path: Path) -> None:
    engine, clock, _ = make_engine(tmp_path)
    engine.reserve_slot()
    clock.mono += 3600

    first = engine.reserve_slot()
    second = engine.reserve_slot()

    assert first == pytest.approx(0.0)
    assert second == pytest.approx(0.2)


def test_reserve_slot_refuses_when_the_queue_is_full_and_does_not_reserve(tmp_path: Path) -> None:
    engine, clock, _ = make_engine(tmp_path, max_queued_requests=3)

    results = [engine.reserve_slot() for _ in range(5)]

    assert results[:3] == pytest.approx([0.0, 0.2, 0.4])
    assert results[3:] == [None, None]
    clock.mono += 0.2
    assert engine.reserve_slot() is not None


@pytest.mark.parametrize("rate", [0, -1, 0.0])
def test_rate_limiter_refuses_a_non_positive_rate(rate: float) -> None:
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=rate, max_queued=1, monotonic=lambda: 0.0)


def test_rate_limiter_never_exceeds_the_rate_over_a_long_horizon() -> None:
    now = [0.0]
    limiter = RateLimiter(requests_per_second=10, max_queued=1000, monotonic=lambda: now[0])

    exits = [now[0] + (limiter.reserve() or 0.0) for _ in range(200)]

    gaps = [b - a for a, b in zip(exits, exits[1:], strict=False)]
    assert min(gaps) >= 0.1 - 1e-9


# ------------------------------------------------------------------------------ auditoria


def test_log_writes_one_json_line_with_names_of_query_params_but_never_their_values(
    tmp_path: Path,
) -> None:
    engine, clock, audit = make_engine(tmp_path)

    engine.log(
        method="GET",
        url=f"{API}/v1/users?token=SEGREDO123&page=2",
        scheme="https",
        at=clock.now(),
        host="api.example.com",
        port=443,
        raw_path="/v1/users",
        raw_query="token=SEGREDO123&page=2",
        verdict=check(engine, "GET", f"{API}/v1/users"),
        status=200,
    )

    text = audit.getvalue()
    record = json.loads(text.strip())
    assert record["query_params"] == ["token", "page"]
    assert "SEGREDO123" not in text
    assert record["run_id"] == RUN_ID
    assert record["decision"] == "allow"
    assert text.count("\n") == 1


def test_log_trips_the_gate_when_the_audit_file_cannot_be_written(tmp_path: Path) -> None:
    class Broken(io.StringIO):
        def write(self, _: str) -> int:
            raise OSError("disco cheio")

    clock = Clock()
    engine = ScopeProxyEngine(
        make_policy(),
        policy_dir=tmp_path,
        audit_file=Broken(),
        stdout=io.StringIO(),
        now=clock.now,
        monotonic=clock.monotonic,
    )
    assert check(engine, "GET", f"{API}/v1/users").allowed

    engine.log(
        method="GET",
        url=f"{API}/v1/users",
        scheme="https",
        at=clock.now(),
        host="api.example.com",
        port=443,
        raw_path="/v1/users",
        raw_query="",
        verdict=check(engine, "GET", f"{API}/v1/users"),
    )

    assert check(engine, "GET", f"{API}/v1/users").reason is Reason.AUDIT_FAILURE


# --------------------------------------------------------------------- endereço resolvido


def test_check_destination_denies_when_any_resolved_address_is_forbidden(tmp_path: Path) -> None:
    engine, _, _ = make_engine(tmp_path)

    verdict = engine.check_destination("api.example.com", 443, ["93.184.216.34", "169.254.169.254"])

    assert verdict.reason is Reason.ADDRESS_FORBIDDEN


@pytest.mark.parametrize("address", ["10.0.0.5", "127.0.0.1", "::1", "192.168.1.1", "100.64.0.1"])
def test_check_destination_denies_private_addresses_for_a_rule_without_allow_local(
    tmp_path: Path, address: str
) -> None:
    engine, _, _ = make_engine(tmp_path)

    assert not engine.check_destination("api.example.com", 443, [address]).allowed


def test_check_destination_allows_a_private_address_only_for_the_allow_local_rule(
    tmp_path: Path,
) -> None:
    engine, _, _ = make_engine(tmp_path)

    assert engine.check_destination("lab.internal", 8080, ["10.1.2.3"]).allowed
    assert not engine.check_destination("lab.internal", 9999, ["10.1.2.3"]).allowed
    assert not engine.check_destination("lab.internal", 8080, ["169.254.169.254"]).allowed
    assert not engine.check_destination("lab.internal", 8080, []).allowed


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "::ffff:169.254.169.254",
        "fd00:ec2::254",
        "fe80::1",
        "0.0.0.0",
        "::",
        "224.0.0.1",
        "255.255.255.255",
        "2002:a9fe:a9fe::1",
        "not-an-ip",
        "",
        "1.1.1.1%eth0",
        "[::1]",
    ],
)
@pytest.mark.parametrize("allow_local", [False, True])
def test_check_addresses_never_allows_metadata_link_local_or_garbage(
    address: str, allow_local: bool
) -> None:
    assert not check_addresses([address], allow_local=allow_local).allowed


def test_check_addresses_denies_an_empty_answer() -> None:
    assert check_addresses([], allow_local=True).reason is Reason.DNS_FAILURE


def test_check_addresses_allows_a_public_address() -> None:
    assert check_addresses(["8.8.8.8", "2606:4700:4700::1111"], allow_local=False).allowed


# ------------------------------------------------------------------------------- política


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": 2},
        {"schema_version": "1"},
        {"schema_version": True},
        {"not_after": 1_799_999_999},
        {"not_after": "2026-11-13T12:00:00"},
        {"not_after": "amanhã"},
        {"run_id": "../x"},
        {"max_queued_requests": 0},
        {"max_queued_requests": 1001},
        {"tls_verify_upstream": "false"},
        {"tls_verify_upstream": False},
        {"extra": 1},
        {"scope": {"allow": [], "deny_paths": []}},
        {
            "limits": {
                "requests_per_second": 0,
                "max_duration_minutes": 60,
                "zap_threads_per_host": 2,
            }
        },
    ],
)
def test_parse_policy_refuses_invalid_or_unsafe_policies(mutation: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        parse_policy(json.dumps(policy_data(**mutation)).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"\xff\xfe",
        b'{"schema_version": 1, "schema_version": 1}',
        b'{"schema_version": NaN}',
        b'{"schema_version": Infinity}',
    ],
)
def test_parse_policy_refuses_malformed_json(raw: bytes) -> None:
    with pytest.raises(ConfigError):
        parse_policy(raw)


def test_parse_policy_refuses_a_duplicate_key_that_would_hide_a_restriction() -> None:
    text = json.dumps(policy_data())
    duplicated = text[:-1] + ', "not_after": "2099-01-01T00:00:00+00:00"}'

    with pytest.raises(ConfigError):
        parse_policy(duplicated.encode())


def test_parse_policy_error_never_echoes_the_offending_value() -> None:
    with pytest.raises(ConfigError) as caught:
        parse_policy(json.dumps(policy_data(run_id="SEGREDO-ABC/../x")).encode())

    assert "SEGREDO-ABC" not in caught.value.message
