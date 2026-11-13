"""Formato das linhas de auditoria."""

import json
from datetime import UTC, datetime

from harness_dast.domain.audit import decision_entry, result_entry
from harness_dast.domain.http_messages import HttpRequest

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def request(url: str) -> HttpRequest:
    return HttpRequest(
        method="POST",
        url=url,
        headers=(("Authorization", "Bearer segredo-xyz"),),
        body=b'{"senha":"segredo-xyz"}',
        operation_id="criar",
        account="user_a",
        route="zap",
    )


def test_decision_line_has_the_request_identity_and_nothing_sensitive() -> None:
    entry = decision_entry(
        3, NOW, request("https://h.example.net:8443/api/x?token=segredo-xyz&b=2")
    )

    assert (entry.seq, entry.phase, entry.decision) == (3, "decision", "allowed")
    assert (entry.scheme, entry.host, entry.port, entry.path) == (
        "https",
        "h.example.net",
        8443,
        "/api/x",
    )
    assert entry.query_names == ("token", "b")
    assert entry.account == "user_a"
    assert entry.operation_id == "criar"
    assert entry.route == "zap"
    assert "segredo-xyz" not in json.dumps(entry.model_dump())


def test_a_denied_decision_carries_the_reason() -> None:
    entry = decision_entry(1, NOW, request("https://h.example.net/api/x"), reason="fora do escopo")

    assert (entry.decision, entry.reason) == ("denied", "fora do escopo")


def test_default_ports_are_filled_in() -> None:
    assert decision_entry(1, NOW, request("https://h.example.net/x")).port == 443
    assert decision_entry(1, NOW, request("http://h.example.net/x")).port == 80


def test_a_malformed_port_does_not_break_the_audit() -> None:
    entry = decision_entry(1, NOW, request("https://h.example.net:abc/x"), reason="malformada")

    assert entry.port == 0
    assert entry.decision == "denied"


def test_result_line_has_status_duration_and_error() -> None:
    ok = result_entry(
        3, NOW, request("https://h.example.net/x"), status=201, error=None, duration_ms=12
    )
    failed = result_entry(
        4,
        NOW,
        request("https://h.example.net/x"),
        status=None,
        error="TARGET_TIMEOUT",
        duration_ms=15000,
    )

    assert (ok.phase, ok.status, ok.duration_ms, ok.error) == ("result", 201, 12, None)
    assert (failed.status, failed.error) == (None, "TARGET_TIMEOUT")
    assert ok.timestamp == NOW.isoformat()
