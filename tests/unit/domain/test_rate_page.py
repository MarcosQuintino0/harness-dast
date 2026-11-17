"""Tamanho de página sem limite: escolha do parâmetro, teto, veredito e achado (ADR 0101)."""

import json

import pytest

from harness_dast.domain.api_model import Operation, Parameter
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.rate_page import (
    PAGE_MAX_OPERATIONS,
    PAGE_PROBE_SIZE,
    PageReply,
    count_items,
    is_page_param,
    judge_page,
    page_alert,
    plan_page_checks,
    probe_size,
    read_reply,
    render_huge_target,
)
from harness_dast.domain.zap_alert import RawAlert

INT = Schema(type="integer")


def op(
    operation_id: str, name: str = "limit", schema: Schema = INT, path: str = "/items"
) -> Operation:
    return Operation(
        operation_id=operation_id,
        method="get",
        path=path,
        parameters=(Parameter(name=name, location="query", value_schema=schema),),
    )


def ex(operation_id: str, target: str = "/items?limit=10", method: str = "GET") -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=operation_id,
        method=method,
        path=target.split("?")[0],
        target=target,
        account="user_a",
        status=200,
    )


def allow_all(method: str, target: str) -> bool:
    return True


@pytest.mark.parametrize("name", ["limit", "page_size", "pageSize", "per_page", "perPage", "size"])
def test_is_page_param_accepts_the_usual_names(name: str) -> None:
    assert is_page_param(name)


@pytest.mark.parametrize("name", ["offset", "page", "email", "sizeless", "limit_exceeded"])
def test_is_page_param_rejects_other_names(name: str) -> None:
    assert not is_page_param(name)


def test_the_plan_takes_a_proven_get_with_an_integer_page_size() -> None:
    plan = plan_page_checks([ex("a")], {"a": op("a")}, permits=allow_all)

    assert [c.operation_id for c in plan.cases] == ["a"]
    case = plan.cases[0]
    assert (case.param, case.huge_value, case.maximum) == ("limit", PAGE_PROBE_SIZE, None)
    assert case.huge_target == f"/items?limit={PAGE_PROBE_SIZE}"


def test_the_plan_ignores_non_integer_non_get_and_unproven_operations() -> None:
    operations = {
        "text": op("text", schema=Schema(type="string")),
        "other": op("other", name="offset"),
        "post": op("post"),
    }
    exchanges = [ex("text"), ex("other"), ex("post", method="POST"), ex("missing")]

    plan = plan_page_checks(exchanges, operations, permits=allow_all)

    assert plan.cases == ()


def test_a_declared_maximum_sets_the_value_just_above_it() -> None:
    bounded = op("a", schema=Schema(type="integer", maximum=100))

    plan = plan_page_checks([ex("a")], {"a": bounded}, permits=allow_all)

    assert (plan.cases[0].huge_value, plan.cases[0].maximum) == (1100, 100)


def test_a_contract_that_already_allows_huge_sizes_is_skipped_not_forced() -> None:
    huge = op("a", schema=Schema(type="integer", maximum=1_000_000))

    plan = plan_page_checks([ex("a")], {"a": huge}, permits=allow_all)

    assert plan.cases == ()
    assert [(s.subject, s.reason) for s in plan.skipped] == [("a", "contract_allows_huge")]


def test_the_fence_denying_the_target_means_no_request() -> None:
    plan = plan_page_checks([ex("a")], {"a": op("a")}, permits=lambda m, t: False)

    assert plan.cases == ()
    assert [s.reason for s in plan.skipped] == ["not_allowed_by_scope"]


def test_the_hard_cap_limits_the_operations_per_run() -> None:
    names = [f"op{i}" for i in range(PAGE_MAX_OPERATIONS + 2)]
    operations = {n: op(n, path=f"/{n}") for n in names}
    exchanges = [ex(n, f"/{n}?limit=10") for n in names]

    plan = plan_page_checks(exchanges, operations, permits=allow_all, max_operations=99)

    assert len(plan.cases) == PAGE_MAX_OPERATIONS
    assert [s.reason for s in plan.skipped] == ["budget_exceeded"] * 2


def test_only_and_infrastructure_paths_are_respected() -> None:
    operations = {"a": op("a"), "b": op("b", path="/b")}
    exchanges = [ex("a"), ex("b", "/b?limit=10")]

    plan = plan_page_checks(
        exchanges,
        operations,
        permits=allow_all,
        infrastructure=frozenset({"/b"}),
        only=frozenset({"a", "b"}),
    )

    assert [c.operation_id for c in plan.cases] == ["a"]


def test_render_huge_target_replaces_or_appends_the_parameter() -> None:
    assert render_huge_target("/x?limit=10&q=a", "limit", 5000) == "/x?limit=5000&q=a"
    assert render_huge_target("/x", "limit", 5000) == "/x?limit=5000"


def test_probe_size_without_maximum_is_the_fixed_value() -> None:
    assert probe_size(None) == PAGE_PROBE_SIZE


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (json.dumps([1, 2, 3]).encode(), 3),
        (json.dumps({"items": [1, 2], "total": 9}).encode(), 2),
        (json.dumps({"data": {"rows": [1, 2, 3, 4]}}).encode(), 4),
        (json.dumps({"ok": True}).encode(), None),
        (b"not json", None),
    ],
)
def test_count_items_reads_the_largest_list(body: bytes, expected: int | None) -> None:
    assert count_items(body) == expected


def reply(
    status: int | None, items: int | None, size: int = 100, truncated: bool = False
) -> PageReply:
    return PageReply(status=status, items=items, size=size, truncated=truncated)


def test_more_items_than_the_normal_request_is_accepted_without_a_declared_maximum() -> None:
    verdict = judge_page(reply(200, 10), reply(200, 240), None)

    assert verdict.outcome == "accepted"
    assert "240" in verdict.detail


def test_a_declared_maximum_is_the_bar_when_there_is_one() -> None:
    assert judge_page(reply(200, 10), reply(200, 100), 100).outcome == "limited"
    assert judge_page(reply(200, 10), reply(200, 101), 100).outcome == "accepted"


def test_the_target_capping_the_size_is_a_limit() -> None:
    assert judge_page(reply(200, 10), reply(200, 10), None).outcome == "limited"
    assert judge_page(reply(200, 10), reply(400, None), None).outcome == "limited"


def test_a_failed_normal_request_is_inconclusive() -> None:
    assert judge_page(reply(500, None), reply(200, 50), None).outcome == "inconclusive"


def test_without_counts_the_body_size_decides() -> None:
    assert judge_page(reply(200, None, 100), reply(200, None, 900), None).outcome == "accepted"
    assert judge_page(reply(200, None, 100), reply(200, None, 150), None).outcome == "inconclusive"


def test_read_reply_ignores_the_count_of_a_truncated_body() -> None:
    assert read_reply(200, b"[1,2", truncated=True).items is None


def test_the_alert_is_medium_cwe_770_and_carries_no_body_values() -> None:
    plan = plan_page_checks([ex("a")], {"a": op("a")}, permits=allow_all)

    alert = page_alert(
        1, plan.cases[0], "o pedido enorme devolveu 240 itens", base_url="http://crapi"
    )

    parsed = RawAlert.model_validate(alert)
    assert (alert["risk"], alert["cweid"], alert["param"]) == ("Medium", "770", "limit")
    assert parsed.url == "http://crapi/items"
    assert "240 itens" in alert["evidence"]


def test_empty_lists_in_both_requests_are_inconclusive_not_a_limit() -> None:
    assert judge_page(reply(200, 0), reply(200, 0), None).outcome == "inconclusive"
