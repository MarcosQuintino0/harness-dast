"""SSRF guiado pelo contrato: escolha dos campos, teto, token, correlação e achado (ADR 0100)."""

import json

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, Parameter, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.oast_ssrf import (
    SSRF_MAX_PER_OPERATION,
    SSRF_MAX_REQUESTS,
    OastEvent,
    SsrfCase,
    callback_url,
    correlate,
    field_reason,
    make_token,
    observation_alert,
    plan_ssrf,
    render_case,
)
from harness_dast.domain.probe_exchange import ExchangeRecord
from harness_dast.domain.zap_alert import RawAlert

STR = Schema(type="string")
BASE = "http://crapi"


def op(
    operation_id: str,
    method: str = "post",
    body: dict[str, Schema] | None = None,
    query: tuple[str, ...] = (),
    path: str = "/x",
) -> Operation:
    request_body = None
    if body is not None:
        schema = Schema(type="object", properties=body)
        request_body = RequestBody(
            required=True, media=(MediaBody(media_type="application/json", body_schema=schema),)
        )
    parameters = tuple(
        Parameter(name=name, location="query", required=False, value_schema=STR) for name in query
    )
    return Operation(
        operation_id=operation_id,
        method=method,  # type: ignore[arg-type]  # o modelo valida o texto livre do teste
        path=path,
        parameters=parameters,
        request_body=request_body,
    )


def ex(
    operation_id: str,
    body: dict[str, object] | None = None,
    method: str = "POST",
    target: str = "/x",
    path: str = "/x",
) -> ExchangeRecord:
    return ExchangeRecord(
        operation_id=operation_id,
        method=method,
        path=path,
        target=target,
        account="user_a",
        status=200,
        content_type="application/json" if body is not None else None,
        body=json.dumps(body) if body is not None else None,
    )


def allow_all(method: str, target: str) -> bool:
    return True


@pytest.mark.parametrize(
    ("name", "schema", "expected"),
    [
        ("mechanic_api", STR, "name"),
        ("callbackUrl", STR, "name"),
        ("return_url", STR, "name"),
        ("webhook", STR, "name"),
        ("image_uri", STR, "name"),
        ("profileHref", STR, "name"),
        ("anything", Schema(type="string", format="uri"), "format"),
        ("anything", Schema(type="string", format="URL"), "format"),
        ("anything", Schema(format="uri-reference"), "format"),
        ("title", STR, None),
        ("urlencoded_note", STR, None),
        ("capital", STR, None),
        ("api_key", STR, None),
        ("token_url", STR, None),
        ("page_url", Schema(type="integer"), None),
    ],
)
def test_field_reason_follows_the_generic_rule(
    name: str, schema: Schema, expected: str | None
) -> None:
    assert field_reason(name, schema) == expected


def test_plan_picks_url_fields_in_body_and_query_and_leaves_the_rest() -> None:
    operations = {
        "contact": op(
            "contact", body={"mechanic_api": STR, "vin": STR, "n": Schema(type="number")}
        ),
        "fetch": op("fetch", "get", query=("source_url", "q"), path="/f"),
    }
    exchanges = [
        ex("contact", {"mechanic_api": "http://x", "vin": "V", "n": 1}),
        ex("fetch", target="/f?source_url=http%3A%2F%2Fa&q=1", method="GET", path="/f"),
    ]

    plan = plan_ssrf(exchanges, operations, permits=allow_all, seed=1)

    assert [(c.operation_id, c.location, c.field) for c in plan.cases] == [
        ("contact", "body", "mechanic_api"),
        ("fetch", "query", "source_url"),
    ]
    assert plan.skipped == ()


def test_tokens_are_unique_per_field_and_operation_and_depend_on_the_seed() -> None:
    tokens = {
        make_token(1, "a", "body", "x_url"),
        make_token(1, "b", "body", "x_url"),
        make_token(1, "a", "body", "y_url"),
        make_token(1, "a", "query", "x_url"),
        make_token(2, "a", "body", "x_url"),
    }

    assert len(tokens) == 5
    assert make_token(1, "a", "body", "x_url") == make_token(1, "a", "body", "x_url")
    assert all(item.startswith("hd") and len(item) == 18 for item in tokens)


def test_method_not_allowed_by_the_approved_scope_is_not_sent() -> None:
    operations = {"contact": op("contact", body={"mechanic_api": STR})}
    exchanges = [ex("contact", {"mechanic_api": "http://x"})]

    plan = plan_ssrf(exchanges, operations, permits=lambda m, t: m == "GET", seed=1)

    assert plan.cases == ()
    assert [(s.operation_id, s.reason) for s in plan.skipped] == [("contact", "method_not_allowed")]


def test_delete_infrastructure_and_unselected_operations_never_enter_the_plan() -> None:
    operations = {
        "gone": op("gone", "delete", query=("target_url",)),
        "login": op("login", body={"callback_url": STR}),
        "other": op("other", body={"callback_url": STR}),
        "chosen": op("chosen", body={"callback_url": STR}),
    }
    exchanges = [
        ex("gone", method="DELETE", target="/x?target_url=a"),
        ex("login", {"callback_url": "a"}, path="/login"),
        ex("other", {"callback_url": "a"}),
        ex("chosen", {"callback_url": "a"}),
    ]

    plan = plan_ssrf(
        exchanges,
        operations,
        permits=allow_all,
        seed=1,
        infrastructure=frozenset({"/login"}),
        only=frozenset({"chosen", "gone", "login"}),
    )

    assert [c.operation_id for c in plan.cases] == ["chosen"]


def test_secret_like_names_and_non_string_values_are_not_chosen() -> None:
    operations = {"o": op("o", body={"password_url": STR, "callback": Schema(type="integer")})}

    plan = plan_ssrf(
        [ex("o", {"password_url": "a", "callback": 3})], operations, permits=allow_all, seed=1
    )

    assert plan.cases == ()


def test_hard_cap_per_operation_and_per_run() -> None:
    wide = {f"hook_{i}_url": STR for i in range(8)}
    operations = {f"op{n}": op(f"op{n}", body=wide) for n in range(6)}
    exchanges = [ex(f"op{n}", {name: "a" for name in wide}) for n in range(6)]

    plan = plan_ssrf(exchanges, operations, permits=allow_all, seed=1, max_requests=500)

    assert len(plan.cases) == SSRF_MAX_REQUESTS
    per_operation: dict[str, int] = {}
    for case in plan.cases:
        per_operation[case.operation_id] = per_operation.get(case.operation_id, 0) + 1
    assert max(per_operation.values()) <= SSRF_MAX_PER_OPERATION
    assert {s.reason for s in plan.skipped} == {"budget_exceeded"}
    assert len(plan.skipped) == 6 * SSRF_MAX_PER_OPERATION - SSRF_MAX_REQUESTS


def test_a_lower_requested_cap_is_respected_and_zero_sends_nothing() -> None:
    operations = {"o": op("o", body={"a_url": STR, "b_url": STR})}
    exchanges = [ex("o", {"a_url": "x", "b_url": "y"})]

    assert (
        len(plan_ssrf(exchanges, operations, permits=allow_all, seed=1, max_requests=1).cases) == 1
    )
    assert plan_ssrf(exchanges, operations, permits=allow_all, seed=1, max_requests=0).cases == ()


def test_render_replaces_only_the_chosen_body_field_with_the_callback_url() -> None:
    operations = {"c": op("c", body={"mechanic_api": STR, "vin": STR})}
    case = plan_ssrf(
        [ex("c", {"mechanic_api": "http://orig", "vin": "V1"})],
        operations,
        permits=allow_all,
        seed=3,
    ).cases[0]

    target, body = render_case(case)

    assert target == "/x"
    assert json.loads(body or "") == {"mechanic_api": callback_url(case.token), "vin": "V1"}


def test_render_replaces_only_the_chosen_query_field() -> None:
    operations = {"f": op("f", "get", query=("source_url", "q"), path="/f")}
    case = plan_ssrf(
        [ex("f", target="/f?q=1&source_url=http%3A%2F%2Fa", method="GET", path="/f")],
        operations,
        permits=allow_all,
        seed=3,
    ).cases[0]

    target, body = render_case(case)

    assert target.startswith("/f?q=1&source_url=http%3A%2F%2Foast-gateway%3A8090%2F")
    assert target.endswith(case.token)
    assert body is None


def _plan_two() -> tuple[SsrfCase, SsrfCase]:
    operations = {"c": op("c", body={"mechanic_api": STR, "other_url": STR})}
    plan = plan_ssrf(
        [ex("c", {"mechanic_api": "a", "other_url": "b"}, target="/x/9")],
        operations,
        permits=allow_all,
        seed=7,
    )
    return plan.cases[0], plan.cases[1]


def test_correlation_matches_events_by_token_and_ignores_strangers_and_duplicates() -> None:
    first, second = _plan_two()
    plan_cases = [first, second]
    events = [
        OastEvent(event_id=9, path="/outro"),
        OastEvent(event_id=8, path=f"/{first.token}", at="2026-11-17T15:00:00+00:00"),
        OastEvent(event_id=7, path=f"/{first.token}"),
    ]

    found = correlate(plan_cases, {first.token: 200, second.token: 200}, events, base_url=BASE)

    assert len(found) == 1
    assert found[0].field == "mechanic_api"
    assert found[0].event.event_id == 7  # o primeiro evento daquele token
    assert found[0].target_path == "/x/9"
    assert found[0].status == 200


def test_no_event_means_no_observation() -> None:
    first, second = _plan_two()
    plan_cases = [first, second]

    assert correlate(plan_cases, {}, [], base_url=BASE) == ()


def test_alert_has_the_proof_of_the_return_and_parses_as_a_zap_alert() -> None:
    first, _ = _plan_two()
    plan_cases = [first, _]
    event = OastEvent(
        event_id=42,
        path=f"/{first.token}",
        at="2026-11-17T15:00:00+00:00",
        user_agent="python-requests/2",
    )
    observation = correlate(plan_cases, {first.token: 200}, [event], base_url=BASE)[0]

    alert = observation_alert(1, observation, base_url=BASE)
    raw = RawAlert.model_validate(alert)

    assert (raw.risk, raw.confidence, raw.cwe_id) == ("High", "High", "918")
    assert (raw.method, raw.url, raw.param) == ("POST", "http://crapi/x/9", "mechanic_api")
    assert raw.input_vector == "json"
    for expected in ("42", "2026-11-17T15:00:00+00:00", "oast-gateway:8090", "python-requests/2"):
        assert expected in raw.evidence
    assert raw.attack == callback_url(first.token)
