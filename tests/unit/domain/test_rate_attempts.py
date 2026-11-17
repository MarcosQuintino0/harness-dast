"""Tentativas sem bloqueio: operações, corpo errado, sinais de limite e teto (ADR 0101)."""

import json

import pytest

from harness_dast.domain.api_model import MediaBody, Operation, RequestBody
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.extra_check_result import ExtraSkip
from harness_dast.domain.rate_attempts import (
    ATTEMPT_MAX_OPERATIONS,
    ATTEMPTS_PER_OPERATION,
    AttemptReply,
    attempts_alert,
    build_attempt_body,
    first_reply_problem,
    guess_kind,
    limit_signal,
    path_words,
    plan_attempts,
    reply_text,
)
from harness_dast.domain.zap_alert import RawAlert

STR = Schema(type="string")


def form(**fields: Schema) -> Schema:
    return Schema(type="object", properties=fields, required=tuple(fields))


OTP_FORM = form(otp=Schema(type="string", max_length=4), email=STR, password=STR)


def op(operation_id: str, path: str, schema: Schema | None, method: str = "post") -> Operation:
    body = None
    if schema is not None:
        media = MediaBody(media_type="application/json", body_schema=schema)
        body = RequestBody(required=True, media=(media,))
    return Operation(operation_id=operation_id, method=method, path=path, request_body=body)  # type: ignore[arg-type]


def allow_all(method: str, target: str) -> bool:
    return True


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("otp", "numeric"),
        ("pin", "numeric"),
        ("password", "secret"),
        ("new_password", "secret"),
        ("code", "code"),
        ("verification_code", "code"),
        ("coupon_code", None),
        ("email", None),
        ("nome", None),
    ],
)
def test_guess_kind_names_the_guess_fields_and_nothing_else(name: str, kind: str | None) -> None:
    assert guess_kind(name) == kind


def test_path_words_split_segments() -> None:
    assert {"check", "otp", "v3"} <= path_words("/identity/api/auth/v3/check-otp")


def test_the_otp_operation_is_chosen_with_a_wrong_body_and_the_test_identity() -> None:
    plan = plan_attempts(
        {"otp": op("otp", "/auth/v2/check-otp", OTP_FORM)},
        identity="conta@lab.test",
        permits=allow_all,
    )

    assert [c.operation_id for c in plan.cases] == ["otp"]
    case = plan.cases[0]
    body = json.loads(case.body)
    assert case.guess_field == "otp"
    assert body["email"] == "conta@lab.test"
    assert body["otp"] == "hdas"  # letras: nunca é um OTP numérico válido
    assert not body["otp"].isdigit()
    assert body["password"] != body["email"]


def test_an_integer_guess_is_below_the_minimum_so_it_can_never_match() -> None:
    schema = form(pin=Schema(type="integer", minimum=1000), email=STR)

    built = build_attempt_body(schema, identity="a@b.test")

    assert isinstance(built, tuple)
    assert json.loads(built[0])["pin"] == 999


def test_a_path_without_an_auth_word_is_not_chosen() -> None:
    plan = plan_attempts(
        {"coupon": op("coupon", "/coupon/validate", form(coupon_code=STR))},
        identity="a@b.test",
        permits=allow_all,
    )

    assert plan.cases == ()
    assert plan.skipped == ()


def test_non_post_path_params_and_non_json_bodies_are_not_chosen() -> None:
    operations = {
        "get": op("get", "/auth/otp", OTP_FORM, method="get"),
        "param": op("param", "/auth/{id}/otp", OTP_FORM),
        "none": op("none", "/auth/otp-none", None),
    }

    assert plan_attempts(operations, identity="a@b.test", permits=allow_all).cases == ()


def test_the_login_path_of_the_profile_is_never_tested() -> None:
    operations = {"login": op("login", "/auth/login", form(email=STR, password=STR))}

    plan = plan_attempts(
        operations,
        identity="a@b.test",
        permits=allow_all,
        infrastructure=frozenset({"/auth/login"}),
    )

    assert plan.cases == ()


def test_without_a_test_identity_the_operation_is_skipped_not_invented() -> None:
    plan = plan_attempts(
        {"otp": op("otp", "/auth/otp", OTP_FORM)}, identity=None, permits=allow_all
    )

    assert plan.cases == ()
    assert plan.skipped == (ExtraSkip(subject="otp", reason="no_test_identity"),)


def test_the_fence_denying_the_path_means_no_request() -> None:
    plan = plan_attempts(
        {"otp": op("otp", "/auth/otp", OTP_FORM)}, identity="a@b.test", permits=lambda m, t: False
    )

    assert plan.cases == ()
    assert [s.reason for s in plan.skipped] == ["not_allowed_by_scope"]


def test_a_required_composite_field_makes_the_body_unsupported() -> None:
    schema = form(otp=STR, extra=Schema(type="object"))

    plan = plan_attempts({"otp": op("otp", "/auth/otp", schema)}, identity=None, permits=allow_all)

    assert [s.reason for s in plan.skipped] == ["unsupported_body"]


def test_the_hard_cap_limits_the_operations_per_run() -> None:
    operations = {f"o{i}": op(f"o{i}", f"/auth/otp{i}", OTP_FORM) for i in range(5)}

    plan = plan_attempts(operations, identity="a@b.test", permits=allow_all, max_operations=99)

    assert len(plan.cases) == ATTEMPT_MAX_OPERATIONS
    assert [s.reason for s in plan.skipped] == ["budget_exceeded"] * 2


def reply(status: int | None, retry_after: str | None = None, text: str = "") -> AttemptReply:
    return AttemptReply(status, retry_after, text)


def test_http_429_and_423_are_limit_signals() -> None:
    assert limit_signal(reply(429), 500) == "http_429"
    assert limit_signal(reply(423), 500) == "http_423"


def test_retry_after_is_a_limit_signal() -> None:
    assert limit_signal(reply(500, "30"), 500) == "retry_after"


def test_a_change_of_status_is_a_limit_signal() -> None:
    assert limit_signal(reply(503), 500) == "status_changed_to_503"


def test_lockout_text_is_a_limit_signal() -> None:
    assert limit_signal(reply(500, text=reply_text(b'{"message":"Account LOCKED"}')), 500) == (
        "lockout_text"
    )


def test_the_same_rejection_every_time_is_no_signal() -> None:
    assert limit_signal(reply(500, text='{"message":"invalid otp"}'), 500) is None


@pytest.mark.parametrize(
    ("status", "problem"),
    [
        (None, "no_response"),
        (200, "unexpected_success"),
        (404, "not_testable_http_404"),
        (422, "not_testable_http_422"),
        (502, "not_testable_http_502"),
        (401, None),
        (500, None),
        (400, None),
    ],
)
def test_first_reply_problem(status: int | None, problem: str | None) -> None:
    assert first_reply_problem(reply(status)) == problem


def test_the_finding_is_medium_with_the_count_and_no_secret() -> None:
    plan = plan_attempts(
        {"otp": op("otp", "/auth/otp", OTP_FORM)}, identity="a@b.test", permits=allow_all
    )

    alert = attempts_alert(1, plan.cases[0], ATTEMPTS_PER_OPERATION, 500, base_url="http://crapi")

    RawAlert.model_validate(alert)
    assert (alert["risk"], alert["cweid"], alert["method"]) == ("Medium", "307", "POST")
    assert f"{ATTEMPTS_PER_OPERATION} tentativas" in alert["evidence"]
    assert "a@b.test" not in json.dumps(alert)
