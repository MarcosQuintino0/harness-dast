"""QA independente (V1.5c): o plano do `negative` com esquemas e pedidos hostis (função pura)."""

import json
import math
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_dast.domain.api_model import MediaBody, Operation, Parameter, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.negative_config import NegativeConfig
from harness_dast.domain.negative_plan import plan_negative
from harness_dast.domain.negative_request import render_case
from harness_dast.domain.negative_values import CLASS_ORDER, MAX_VALUE_CHARS, expected_code
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.schema_check import check_schema

numbers = st.one_of(
    st.integers(min_value=-(2**70), max_value=2**70),
    st.floats(allow_nan=True, allow_infinity=True, width=64),
    st.sampled_from([0, 1, -1, 1e308, -1e308, 0.5, 2**53, 2**53 + 1]),
)
scalars = st.one_of(
    st.none(), st.booleans(), st.integers(), st.text(max_size=8), st.floats(allow_nan=False)
)


@st.composite
def schemas(draw: Any) -> Schema:
    kind = draw(st.sampled_from(["string", "integer", "number", "boolean", None]))
    low = draw(st.one_of(st.none(), numbers))
    high = draw(st.one_of(st.none(), numbers))
    if (
        low is not None
        and high is not None
        and not (isinstance(low, float) and math.isnan(low))
        and not (isinstance(high, float) and math.isnan(high))
        and low > high
    ):
        low, high = high, low
    short = draw(st.one_of(st.none(), st.integers(0, 5000)))
    long = draw(st.one_of(st.none(), st.integers(0, 5000)))
    if short is not None and long is not None and short > long:
        short, long = long, short
    enum = draw(st.one_of(st.none(), st.lists(scalars, max_size=6).map(tuple)))
    try:
        return Schema(
            type=kind,
            minimum=low,
            maximum=high,
            exclusive_minimum=draw(st.booleans()),
            exclusive_maximum=draw(st.booleans()),
            min_length=short,
            max_length=long,
            enum=enum,
            nullable=draw(st.booleans()),
        )
    except ValueError:
        return Schema(type="string")


def _exchange(method: str, target: str, body: dict[str, Any] | None) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id="op",
        method=method,
        path="/api/x",
        target=target,
        account="a",
        status=200,
        content_type="application/json" if body is not None else None,
        body=None if body is None else json.dumps(body),
    )


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(schemas(), schemas(), st.integers(1, 1000))
def test_the_plan_never_raises_and_every_case_is_a_value_the_domain_proves_forbidden(
    query_schema: Schema, body_schema: Schema, limit: int
) -> None:
    operation = Operation(
        operation_id="op",
        method="post",
        path="/api/x",
        parameters=(
            Parameter(name="q", location="query", required=True, value_schema=query_schema),
        ),
        request_body=RequestBody(
            required=True,
            media=(
                MediaBody(
                    media_type="application/json",
                    body_schema=Schema(
                        type="object", properties={"campo": body_schema}, required=("campo",)
                    ),
                ),
            ),
        ),
    )
    exchanges = [
        _exchange("GET", "/api/x?q=1", None),
        _exchange("POST", "/api/x?q=1", {"campo": 1}),
        _exchange("PUT", "/api/x?q=1", {"campo": "a"}),
        _exchange("PATCH", "/api/x?q=1", {"campo": True}),
        _exchange("DELETE", "/api/x?q=1", None),
    ]

    plan = plan_negative(
        exchanges,
        {"op": operation},
        NegativeConfig(allow_writes=True),
        max_requests=limit,
    )

    assert len(plan.cases) <= limit
    assert all(case.exchange.method.upper() != "DELETE" for case in plan.cases)
    assert all(case.case_class in CLASS_ORDER for case in plan.cases)
    for case in plan.cases:
        target, body = render_case(case)
        assert target.startswith("/")
        assert "\n" not in target
        if body is not None:
            json.loads(body)
        if case.remove:
            continue
        assert len(str(case.value)) <= MAX_VALUE_CHARS
        flat = query_schema if case.location == "query" else body_schema
        assert check_schema(flat, case.value) == (expected_code(case.case_class),) or (
            case.location == "query"
        )


@pytest.mark.parametrize("method", ["GET", "get"])
def test_the_plan_without_the_letter_has_no_write_case_for_any_schema(method: str) -> None:
    operation = Operation(
        operation_id="op",
        method="post",
        path="/api/x",
        request_body=RequestBody(
            required=True,
            media=(
                MediaBody(
                    media_type="application/json",
                    body_schema=Schema(
                        type="object",
                        properties={"n": Schema(type="integer", minimum=1, maximum=2)},
                        required=("n",),
                    ),
                ),
            ),
        ),
    )
    exchanges = [
        _exchange("POST", "/api/x", {"n": 1}),
        _exchange("PUT", "/api/x", {"n": 1}),
        _exchange("PATCH", "/api/x", {"n": 1}),
        _exchange(method, "/api/x", None),
    ]

    plan = plan_negative(exchanges, {"op": operation}, NegativeConfig(), max_requests=100)

    assert all(case.exchange.method.upper() == "GET" for case in plan.cases)
    assert {n.reason for n in plan.not_tested} >= {"writes_not_authorized"}


@pytest.mark.parametrize(
    "budget",
    [
        0,
        -1,
    ],
)
def test_a_zero_or_negative_budget_plans_nothing(budget: int) -> None:
    operation = Operation(
        operation_id="op",
        method="get",
        path="/api/x",
        parameters=(
            Parameter(
                name="q",
                location="query",
                value_schema=Schema(type="integer", minimum=1, maximum=2),
            ),
        ),
    )

    plan = plan_negative(
        [_exchange("GET", "/api/x?q=1", None)],
        {"op": operation},
        NegativeConfig(),
        max_requests=budget,
    )

    assert plan.cases == ()


def test_a_query_value_with_reserved_characters_in_the_baseline_is_re_encoded_not_split() -> None:
    operation = Operation(
        operation_id="op",
        method="get",
        path="/api/x",
        parameters=(
            Parameter(name="q", location="query", value_schema=Schema(type="integer", minimum=1)),
            Parameter(name="o", location="query", value_schema=Schema(type="string", max_length=3)),
        ),
    )
    exchange = _exchange("GET", "/api/x?q=1&o=a%26b%3Dc%23d%0Ae", None)

    plan = plan_negative([exchange], {"op": operation}, NegativeConfig(), max_requests=10)

    assert plan.cases
    for case in plan.cases:
        target, _ = render_case(case)
        assert "\n" not in target
        assert "#" not in target
        assert target.count("?") == 1
        assert len(target.split("?")[1].split("&")) == 2
