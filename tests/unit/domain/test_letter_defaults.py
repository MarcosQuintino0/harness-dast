"""Padrões mínimos da CLI para "não sei" na carta (ADR 0114): só quatro campos, com aviso."""

from datetime import date
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_defaults import (
    MINIMUM_DEFAULTS,
    default_notes,
    read_default_notes,
)
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from tests.fakes.letter_data import answer, valid_letter_data

UNKNOWN = {"source": "desconhecido"}
CASES = [
    ("limits", "requests_per_second", "limits.requests_per_second", 5, 1),
    ("limits", "max_duration_minutes", "limits.max_duration_minutes", 60, 30),
    ("limits", "zap_threads_per_host", "limits.zap_threads_per_host", 2, 1),
    ("auth", "login_max_per_minute", "auth.login_max_per_minute", 5, 1),
]


def _review(data: dict[str, Any]) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", date(2026, 11, 14))


def _profile(review: LetterReview) -> ProductProfile:
    assert review.profile_text is not None
    return ProductProfile.from_data(parse_profile_yaml(review.profile_text))


def _value(profile: ProductProfile, field: str) -> object:
    if field == "auth.login_max_per_minute":
        assert profile.auth.type == "login_password"
        assert profile.auth.login_limit is not None
        return profile.auth.login_limit.max_per_minute
    return getattr(profile.limits, field.split(".")[1])


def _warned(review: LetterReview) -> set[str]:
    return {w.field for w in review.warnings if w.code == "MINIMUM_DEFAULT_APPLIED"}


def test_table_has_exactly_the_four_documented_fields() -> None:
    assert set(MINIMUM_DEFAULTS) == {case[2] for case in CASES}
    assert all(default.reason for default in MINIMUM_DEFAULTS.values())


@pytest.mark.parametrize(("section", "name", "field", "given", "minimum"), CASES)
def test_review_uses_the_minimum_when_the_answer_is_unknown(
    section: str, name: str, field: str, given: int, minimum: int
) -> None:
    data = valid_letter_data()
    data[section][name] = UNKNOWN

    review = _review(data)

    assert review.ready
    assert _value(_profile(review), field) == minimum
    assert _warned(review) == {field}
    message = next(w.message for w in review.warnings if w.field == field)
    assert f"{field} = {minimum}" in message
    assert "padrão mínimo da cli" in message.lower()


@pytest.mark.parametrize(("section", "name", "field", "given", "minimum"), CASES)
@pytest.mark.parametrize("source", ["carta", "pessoa"])
def test_review_keeps_the_given_value_when_the_answer_has_one(
    section: str, name: str, field: str, given: int, minimum: int, source: str
) -> None:
    data = valid_letter_data()
    data[section][name] = answer(given, source)

    review = _review(data)

    assert review.ready
    assert _value(_profile(review), field) == given
    assert _warned(review) == set()


def test_review_applies_every_minimum_at_once_and_records_them_in_the_profile_header() -> None:
    data = valid_letter_data()
    for section, name, *_ in CASES:
        data[section][name] = UNKNOWN

    review = _review(data)

    assert _warned(review) == {case[2] for case in CASES}
    assert review.profile_text is not None
    assert sorted(read_default_notes(review.profile_text)) == [
        "auth.login_max_per_minute = 1",
        "limits.max_duration_minutes = 30",
        "limits.requests_per_second = 1",
        "limits.zap_threads_per_host = 1",
    ]


def test_review_has_no_default_note_or_warning_when_nothing_was_unknown() -> None:
    review = _review(valid_letter_data())

    assert review.profile_text is not None
    assert read_default_notes(review.profile_text) == ()
    assert _warned(review) == set()


@pytest.mark.parametrize("field", ["limits.requests_per_second", "limits.max_duration_minutes"])
def test_review_still_reports_a_missing_limit_instead_of_defaulting(field: str) -> None:
    data = valid_letter_data()
    section, name = field.split(".")
    del data[section][name]

    review = _review(data)

    assert {i.field: i.code for i in review.issues} == {field: "MISSING"}
    assert review.warnings == ()


@pytest.mark.parametrize("value", ["muito", -1, 0, [], True])
def test_review_refuses_an_invalid_limit_instead_of_defaulting(value: object) -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = answer(value)

    review = _review(data)

    assert not review.ready
    assert review.profile_text is None
    assert review.warnings == ()


def test_review_does_not_default_the_login_limit_on_an_api_key_letter() -> None:
    data = valid_letter_data()
    data["auth"] = {
        "type": answer("api_key", "pessoa"),
        "header_name": answer("X-API-Key", "pessoa"),
        "login_max_per_minute": UNKNOWN,
        "accounts": answer(
            [{"alias": "svc_a", "role": "servico", "api_key": {"secret_ref": "env:ACME_SVC_KEY"}}]
        ),
    }

    review = _review(data)

    assert {i.field: i.code for i in review.issues} == {
        "auth.login_max_per_minute": "INVALID_VALUE"
    }
    assert _warned(review) == set()


@pytest.mark.parametrize(
    "field",
    [
        "gates.test_environment",
        "gates.synthetic_data",
        "gates.authorization_in_force",
        "gates.product_owner",
        "environment.base_url",
        "scope.allow",
        "scope.deny_paths",
        "authorization.reference",
        "authorization.valid_until",
        "authorization.windows",
        "auth.type",
        "auth.accounts",
    ],
)
def test_review_keeps_every_gate_stopping_on_an_unknown_answer(field: str) -> None:
    data = valid_letter_data()
    section, name = field.split(".")
    data[section][name] = UNKNOWN

    review = _review(data)

    assert not review.ready
    assert review.profile_text is None
    assert any(i.field == field and i.code == "UNKNOWN" for i in review.issues)
    assert review.warnings == ()


def test_review_does_not_default_when_a_gate_stops_the_letter() -> None:
    data = valid_letter_data()
    data["limits"]["requests_per_second"] = UNKNOWN
    data["scope"]["deny_paths"] = UNKNOWN

    review = _review(data)

    assert {i.field: i.code for i in review.issues} == {"scope.deny_paths": "UNKNOWN"}
    assert review.warnings == ()


def test_attack_fields_keep_the_narrowest_value_when_unknown() -> None:
    data = valid_letter_data()
    data["scope"]["path_mode"] = UNKNOWN
    data["attack"] = {
        name: UNKNOWN
        for name in (
            "strength",
            "pacing",
            "inject_headers",
            "oast",
            "allow_rate_tests",
            "experimental_rules",
            "inventory",
            "allow_authz_writes",
            "allow_invalid_input_writes",
            "allow_upload_scan",
        )
    }

    review = _review(data)
    profile = _profile(review)

    assert profile.scope.path_mode == "strict"
    assert profile.scan.pacing == "legacy"
    assert not profile.scan.inject_headers
    assert not profile.scan.oast
    assert profile.extra_checks.is_default()
    assert not profile.authz.allow_writes
    assert not profile.negative.allow_writes
    assert not profile.scan.allow_upload_scan
    assert profile.scan.include_outcomes == ()
    assert _warned(review) == set()


def test_default_notes_round_trip_and_ignore_other_comments() -> None:
    defaults = [
        MINIMUM_DEFAULTS["limits.requests_per_second"],
        MINIMUM_DEFAULTS["auth.login_max_per_minute"],
    ]
    text = "# outro comentário\n" + default_notes(defaults) + "schema_version: 1\n"

    assert read_default_notes(text) == (
        "limits.requests_per_second = 1",
        "auth.login_max_per_minute = 1",
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "limits.x = 1\n",
        "# Padrão mínimo da CLI: sem igual\n",
        "#Padrão mínimo da CLI: a = 1 (x)\n",
    ],
)
def test_read_default_notes_ignores_text_that_is_not_a_note(text: str) -> None:
    assert read_default_notes(text) == ()


def test_minimum_defaults_rejects_change_when_code_tries_to_widen_a_value() -> None:
    with pytest.raises(TypeError):
        MINIMUM_DEFAULTS["limits.requests_per_second"] = MINIMUM_DEFAULTS[  # type: ignore[index]  # prova que a tabela é imutável
            "limits.max_duration_minutes"
        ]
