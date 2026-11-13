"""Cliente de varredura do ZAP contra um ZAP falso com as formas de resposta do spike do M0."""

from typing import Any

import pytest

from harness_dast.adapters.zap.scan_client import ZapScanClient
from harness_dast.application.scan_ports import ScanStart
from harness_dast.domain.errors import ExternalToolError
from harness_dast.domain.run import RunLimits
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_policy import build_limits, build_policy
from harness_dast.domain.scan_result import ScanRefused
from harness_dast.domain.scan_tokens import ReplacerRule
from tests.fakes.local_server import Reply, serve
from tests.fakes.zap_scan_server import API_KEY, FakeScanZapServer, ok


def client_for(url: str) -> ZapScanClient:
    return ZapScanClient(url, API_KEY, timeout_seconds=2.0)


def message(identifier: int, **extra: str) -> dict[str, str]:
    return {
        "id": str(identifier),
        "type": "1",
        "requestHeader": f"GET http://alvo/x{identifier} HTTP/1.1\r\nHost: alvo\r\n",
        "requestBody": "",
        "responseHeader": "HTTP/1.1 200 OK\r\n",
        "responseBody": "{}",
        **extra,
    }


def start(**changes: Any) -> ScanStart:
    base = {
        "url": "http://alvo/books/v1",
        "method": "GET",
        "context_id": 3,
        "policy_name": "hdast-scan",
        "max_scan_minutes": 4,
    }
    return ScanStart.model_validate({**base, **changes})


def policy_and_limits() -> Any:
    limits = RunLimits(requests_per_second=5, max_duration_minutes=60, zap_threads_per_host=2)
    config = ScanConfig()
    return build_policy(config), build_limits(limits, config)


def test_context_must_exist_with_the_registered_id() -> None:
    zap = FakeScanZapServer()
    with serve(zap) as server:
        client = client_for(server.base_url)
        client.verify_context("hdast-run", 3)
        with pytest.raises(ExternalToolError, match="não existe"):
            client.verify_context("hdast-run", 9)
        with pytest.raises(ExternalToolError, match=r"não existe|recusou"):
            client.verify_context("outro", 3)


def test_the_key_travels_in_a_header_never_in_the_url() -> None:
    with serve(FakeScanZapServer()) as server:
        client_for(server.base_url).verify_context("hdast-run", 3)

    assert API_KEY not in server.requests[0].target


def test_messages_are_listed_across_pages() -> None:
    zap = FakeScanZapServer(messages=[message(n) for n in range(1, 26)])
    with serve(zap) as server:
        found = client_for(server.base_url).list_messages("http://alvo")

    assert [m.id for m in found] == list(range(1, 26))
    assert found[0].type == "1"
    assert "GET http://alvo/x1" in found[0].request_header
    listing = [q for name, q in zap.calls if name == "core/view/messages"]
    assert [q["start"] for q in listing] == ["0", "10", "20"]
    assert {q["baseurl"] for q in listing} == {"http://alvo"}


def test_one_message_is_read_with_headers_and_bodies() -> None:
    zap = FakeScanZapServer(messages=[message(5, responseBody='{"a": 1}')])
    with serve(zap) as server:
        client = client_for(server.base_url)
        found = client.get_message(5)
        with pytest.raises(ExternalToolError):
            client.get_message(6)

    assert found.response_body == '{"a": 1}'


@pytest.mark.parametrize(
    "payload",
    [{"messages": "x"}, {"messages": [{"id": "x"}]}, {"messages": [{"requestHeader": "x"}]}, {}],
)
def test_malformed_message_listings_are_external_tool_errors(payload: dict[str, Any]) -> None:
    with (
        serve(lambda received: ok(payload)) as server,
        pytest.raises(ExternalToolError, match="inesperada"),
    ):
        client_for(server.base_url).list_messages("http://alvo")


def test_policy_sets_limits_first_recreates_the_policy_and_disables_the_rules() -> None:
    zap = FakeScanZapServer()
    zap.policies.add("hdast-scan")
    policy, limits = policy_and_limits()
    with serve(zap) as server:
        client_for(server.base_url).apply_policy(policy, limits)

    assert zap.options["threads"] == "2"
    assert zap.options["delay"] == "200"
    assert zap.options["max_scan"] == "10"
    assert zap.options["max_rule"] == "2"
    assert zap.options["injectable"] == "51"
    assert zap.options["host_per_scan"] == "1"
    assert (zap.options["strength"], zap.options["threshold"]) == ("LOW", "MEDIUM")
    assert zap.policies == {"hdast-scan"}
    assert {"40044", "10104"} <= zap.disabled
    names = zap.endpoints()
    assert names.index("ascan/action/setOptionThreadPerHost") < names.index(
        "ascan/action/addScanPolicy"
    )
    assert names.index("ascan/action/removeScanPolicy") < names.index("ascan/action/addScanPolicy")
    assert names.index("ascan/action/disableScanners") < names.index("ascan/view/scanners")


def test_policy_is_refused_when_a_rule_that_must_be_off_stays_on() -> None:
    zap = FakeScanZapServer(stubborn_rules=frozenset({"40044"}))
    policy, limits = policy_and_limits()
    with serve(zap) as server, pytest.raises(ExternalToolError, match="40044"):
        client_for(server.base_url).apply_policy(policy, limits)


def test_scan_always_sends_context_id_policy_and_no_recursion() -> None:
    zap = FakeScanZapServer(context_regex=r"^http://alvo/.*")
    with serve(zap) as server:
        scan_id = client_for(server.base_url).start_scan(start(method="POST", body='{"a":1}'))

    assert scan_id == "0"
    sent = next(q for name, q in zap.calls if name == "ascan/action/scan")
    assert sent["contextId"] == "3"
    assert sent["scanPolicyName"] == "hdast-scan"
    assert sent["recurse"] == "false"
    assert sent["method"] == "POST"
    assert sent["postData"] == '{"a":1}'
    assert zap.options["max_scan"] == "4"
    names = zap.endpoints()
    assert names.index("ascan/action/setOptionMaxScanDurationInMins") < names.index(
        "ascan/action/scan"
    )


def test_scan_without_body_sends_no_post_data() -> None:
    zap = FakeScanZapServer()
    with serve(zap) as server:
        client_for(server.base_url).start_scan(start())

    sent = next(q for name, q in zap.calls if name == "ascan/action/scan")
    assert "postData" not in sent


def test_a_url_outside_the_context_is_a_refusal_not_a_dead_zap() -> None:
    zap = FakeScanZapServer(context_regex=r"^http://alvo/permitido")
    with serve(zap) as server, pytest.raises(ScanRefused, match="recusou"):
        client_for(server.base_url).start_scan(start(url="http://alvo/outro"))


def test_scan_status_reads_progress_state_and_counts_as_text() -> None:
    zap = FakeScanZapServer(
        scan_states=[
            {"id": "0", "progress": "45", "state": "FINISHED", "reqCount": "9", "alertCount": "3"}
        ]
    )
    with serve(zap) as server:
        status = client_for(server.base_url).scan_status("0")

    assert (status.progress, status.state, status.requests, status.alerts) == (45, "FINISHED", 9, 3)
    assert status.finished is True


def test_scan_status_clamps_garbage_and_rejects_unknown_scans() -> None:
    zap = FakeScanZapServer(scan_states=[{"id": "0", "progress": "250", "state": "running"}])
    with serve(zap) as server:
        client = client_for(server.base_url)
        status = client.scan_status("0")
        with pytest.raises(ExternalToolError, match="não conhece"):
            client.scan_status("7")

    assert (status.progress, status.state, status.finished) == (100, "RUNNING", False)


def test_stop_is_sent_with_the_scan_id() -> None:
    zap = FakeScanZapServer()
    with serve(zap) as server:
        client_for(server.base_url).stop_scan("0")

    assert zap.calls[-1] == ("ascan/action/stop", {"scanId": "0"})


def test_alerts_are_listed_across_pages_with_values_as_text() -> None:
    alerts = [
        {"id": str(n), "alert": "SQL Injection", "tags": {"a": "b"}, "cweid": 89}
        for n in range(120)
    ]
    zap = FakeScanZapServer(alerts=alerts)  # type: ignore[arg-type]
    with serve(zap) as server:
        found = client_for(server.base_url).list_alerts("http://alvo")

    assert len(found) == 120
    assert found[0]["cweid"] == "89"
    assert found[0]["tags"] == '{"a": "b"}'
    assert [q["start"] for name, q in zap.calls if name == "alert/view/alerts"] == [
        "0",
        "50",
        "100",
    ]


def test_replacer_rule_is_added_with_every_parameter_and_removed_by_name() -> None:
    zap = FakeScanZapServer()
    rule = ReplacerRule(
        description="hdast-auth-1-1",
        match_type="REQ_HEADER",
        match_string="Authorization",
        regex=False,
        replacement="Bearer TOKEN-X",
        url="^http://alvo(?::80)?/.*",
    )
    with serve(zap) as server:
        client = client_for(server.base_url)
        client.add_replacer_rule(rule)
        added = dict(zap.rules["hdast-auth-1-1"])
        client.remove_replacer_rule("hdast-auth-1-1")
        with pytest.raises(ExternalToolError):
            client.remove_replacer_rule("hdast-auth-1-1")

    assert added["enabled"] == "true"
    assert added["matchType"] == "REQ_HEADER"
    assert added["matchRegex"] == "false"
    assert added["matchString"] == "Authorization"
    assert added["replacement"] == "Bearer TOKEN-X"
    assert added["url"] == "^http://alvo(?::80)?/.*"
    assert added["initiators"] == ""
    assert zap.rules == {}


def test_scan_policy_removal_is_skipped_when_it_does_not_exist() -> None:
    zap = FakeScanZapServer()
    with serve(zap) as server:
        client = client_for(server.base_url)
        client.remove_scan_policy("hdast-scan")
        zap.policies.add("hdast-scan")
        client.remove_scan_policy("hdast-scan")

    assert zap.endpoints().count("ascan/action/removeScanPolicy") == 1
    assert zap.policies == set()


def test_unknown_policy_listing_shape_is_an_external_tool_error() -> None:
    with (
        serve(lambda received: ok({"scanPolicyNames": "x"})) as server,
        pytest.raises(ExternalToolError, match="inesperada"),
    ):
        client_for(server.base_url).remove_scan_policy("x")


def test_a_wrong_key_is_an_error_without_the_key_in_the_message() -> None:
    with serve(FakeScanZapServer()) as server:
        client = ZapScanClient(server.base_url, "outra-chave", timeout_seconds=2.0)
        with pytest.raises(ExternalToolError) as info:
            client.list_alerts("http://alvo")

    assert "outra-chave" not in info.value.message


def test_a_server_error_without_json_is_an_external_tool_error() -> None:
    with (
        serve(lambda received: Reply(500, b"<html>")) as server,
        pytest.raises(ExternalToolError),
    ):
        client_for(server.base_url).scan_status("0")
