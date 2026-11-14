"""Leitura de `ascan/view/scanProgress`: a forma real do ZAP 2.17.0 e as formas inválidas."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.zap.scan_client import ZapScanClient
from harness_dast.adapters.zap.scan_progress import parse_scan_progress
from harness_dast.domain.errors import ExternalToolError
from tests.fakes.local_server import serve
from tests.fakes.zap_scan_server import API_KEY, FakeScanZapServer

REAL = Path(__file__).resolve().parents[3] / "fixtures" / "zap_real" / "scan_progress_2_17_0.json"


def real_body() -> dict[str, object]:
    body: dict[str, object] = json.loads(REAL.read_text(encoding="utf-8"))
    return body


def wrap(*plugins: list[object]) -> dict[str, object]:
    rows = [{"Plugin": list(plugin)} for plugin in plugins]
    return {"scanProgress": ["http://alvo", {"HostProcess": rows}]}


def plugin(status: str = "Complete", **changes: str) -> list[object]:
    base = {
        "name": "SQL Injection",
        "id": "40018",
        "quality": "release",
        "status": status,
        "ms": "1273",
        "requests": "38",
        "alerts": "1",
    }
    return list({**base, **changes}.values())


def test_real_capture_is_read_with_time_requests_and_alerts_per_rule() -> None:
    rules = parse_scan_progress(real_body())

    by_id = {rule.plugin_id: rule for rule in rules}
    assert len(rules) == 44
    sql = by_id[40018]
    assert (sql.name, sql.state, sql.time_ms, sql.requests, sql.alerts) == (
        "SQL Injection",
        "completed",
        1273,
        38,
        0,
    )
    assert sum(1 for rule in rules if rule.state == "completed") == 43


def test_real_capture_skipped_rule_keeps_a_closed_reason_code_not_the_zap_text() -> None:
    rules = parse_scan_progress(real_body())

    skipped = [rule for rule in rules if rule.state == "skipped"]
    assert [(rule.plugin_id, rule.skip_reason, rule.requests) for rule in skipped] == [
        (40026, "other", 0)
    ]
    assert "browser" not in "".join(rule.model_dump_json() for rule in rules)


@pytest.mark.parametrize(
    ("status", "state", "reason"),
    [
        ("Complete", "completed", None),
        ("Pending", "pending", None),
        ("Running", "interrupted", None),
        ("Skipped, exceeded max rule time.", "skipped", "max_rule_time"),
        ("Skipped, qualquer outro motivo", "skipped", "other"),
        ("Algo novo", "unknown", None),
    ],
)
def test_zap_status_text_becomes_a_closed_state(
    status: str, state: str, reason: str | None
) -> None:
    (rule,) = parse_scan_progress(wrap(plugin(status)))

    assert (rule.state, rule.skip_reason) == (state, reason)


def test_a_time_that_is_not_a_number_is_unknown_not_zero() -> None:
    (rule,) = parse_scan_progress(wrap(plugin(ms="")))

    assert rule.time_ms is None


def test_an_empty_host_process_is_valid_and_has_no_rules() -> None:
    assert parse_scan_progress({"scanProgress": ["http://alvo", {"HostProcess": []}]}) == ()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"scanProgress": "x"},
        {"scanProgress": [{"Other": []}]},
        {"scanProgress": [{"HostProcess": "x"}]},
        {"scanProgress": [{"HostProcess": ["x"]}]},
        {"scanProgress": [{"HostProcess": [{"Plugin": "x"}]}]},
        {"scanProgress": [{"HostProcess": [{"Plugin": ["a", "1"]}]}]},
        {
            "scanProgress": [
                {"HostProcess": [{"Plugin": ["a", "x", "r", "Complete", "1", "1", "1"]}]}
            ]
        },
        {"scanProgress": [{"HostProcess": [{"Plugin": ["a", "1", "r", "Complete", "1", "1", 1]}]}]},
        {
            "scanProgress": [
                {"HostProcess": [{"Plugin": ["a", "-1", "r", "Complete", "1", "1", "1"]}]}
            ]
        },
    ],
)
def test_a_response_out_of_the_known_shape_is_an_external_tool_error(
    body: dict[str, Any],
) -> None:
    with pytest.raises(ExternalToolError, match="inesperada"):
        parse_scan_progress(body)


def test_an_absurd_number_of_rules_is_refused() -> None:
    body = wrap(*[plugin(id=str(n)) for n in range(5001)])

    with pytest.raises(ExternalToolError, match="inesperada"):
        parse_scan_progress(body)


def test_the_client_reads_the_rules_of_one_scan_and_never_puts_the_key_in_the_url() -> None:
    zap = FakeScanZapServer(scan_progress=real_body())
    with serve(zap) as server:
        client = ZapScanClient(server.base_url, API_KEY, timeout_seconds=2.0)
        rules = client.scan_rules("0")

    assert len(rules) == 44
    sent = next(q for name, q in zap.calls if name == "ascan/view/scanProgress")
    assert sent["scanId"] == "0"
    assert API_KEY not in server.requests[0].target


def test_the_client_turns_an_unknown_scan_into_an_external_tool_error() -> None:
    with serve(FakeScanZapServer(scan_progress=real_body())) as server:
        client = ZapScanClient(server.base_url, API_KEY, timeout_seconds=2.0)
        with pytest.raises(ExternalToolError):
            client.scan_rules("99")
