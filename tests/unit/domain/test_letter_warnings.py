"""Validade vencida e avisos da carta (ADR 0036): o que recusa e o que só avisa."""

from datetime import date
from typing import Any

from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from tests.fakes.letter_data import answer, valid_letter_data

TODAY = date(2026, 11, 14)


def _letter(**changes: Any) -> dict[str, Any]:
    data = valid_letter_data()
    data["authorization"]["valid_until"] = answer("2027-06-30")
    data["scope"]["deny_paths"] = answer(["/api/admin/**"])
    for dotted, value in changes.items():
        *parents, last = dotted.split("__")
        node = data
        for key in parents:
            node = node[key]
        node[last] = value
    return data


def _review(data: dict[str, Any], today: date = TODAY) -> LetterReview:
    return review_letter(Letter.from_data(data), "demo", today)


def _codes(review: LetterReview) -> list[str]:
    return [warning.code for warning in review.warnings]


def test_authorization_expired_yesterday_is_refused_with_its_own_code() -> None:
    review = _review(_letter(authorization__valid_until=answer("2026-11-13")))

    assert not review.ready
    assert review.profile_text is None
    assert [(i.field, i.code) for i in review.issues] == [
        ("authorization.valid_until", "AUTHORIZATION_EXPIRED")
    ]
    assert "peça ao dono do produto" in review.issues[0].message.lower()


def test_authorization_valid_until_today_is_still_valid_because_the_last_day_counts() -> None:
    review = _review(_letter(authorization__valid_until=answer("2026-11-14")))

    assert review.ready


def test_expiry_uses_the_day_passed_in_and_never_the_real_clock() -> None:
    data = _letter(authorization__valid_until=answer("2027-06-30"))

    assert _review(data, date(2027, 6, 30)).ready
    assert not _review(data, date(2027, 7, 1)).ready


def test_a_clean_letter_has_no_warnings() -> None:
    review = _review(_letter())

    assert review.ready
    assert review.warnings == ()


def test_root_wildcard_in_allow_is_a_warning_and_does_not_block() -> None:
    rule = [{"host": "api.hml.acme-teste.net.br", "paths": ["/**"], "methods": ["GET", "POST"]}]

    review = _review(_letter(scope__allow=answer(rule)))

    assert review.ready
    assert _codes(review) == ["ALLOW_ROOT_WILDCARD"]
    assert review.warnings[0].field == "scope.allow[0].paths"


def test_delete_method_authorized_is_a_warning_and_does_not_block() -> None:
    rule = [
        {
            "host": "api.hml.acme-teste.net.br",
            "paths": ["/api/**"],
            "methods": ["GET", "POST", "DELETE"],
        }
    ]

    review = _review(_letter(scope__allow=answer(rule)))

    assert review.ready
    assert _codes(review) == ["DELETE_AUTHORIZED"]
    assert review.warnings[0].field == "scope.allow[0].methods"


def test_empty_deny_paths_is_a_warning_and_does_not_block() -> None:
    review = _review(_letter(scope__deny_paths=answer([])))

    assert review.ready
    assert _codes(review) == ["DENY_PATHS_EMPTY"]


def test_validity_beyond_one_year_is_a_warning_and_exactly_one_year_is_not() -> None:
    assert _codes(_review(_letter(authorization__valid_until=answer("2027-11-15")))) == [
        "VALIDITY_OVER_ONE_YEAR"
    ]
    assert _codes(_review(_letter(authorization__valid_until=answer("2027-11-14")))) == []


def test_warnings_never_change_the_generated_profile() -> None:
    plain = _review(_letter())
    rule = [
        {
            "host": "api.hml.acme-teste.net.br",
            "paths": ["/**"],
            "methods": ["GET", "POST", "DELETE"],
        }
    ]
    loud = _review(_letter(scope__allow=answer(rule), scope__deny_paths=answer([])))

    assert loud.warnings
    assert plain.profile_text is not None
    assert loud.profile_text is not None
    assert "DELETE" in loud.profile_text
    assert [w.code for w in loud.warnings] == [
        "ALLOW_ROOT_WILDCARD",
        "DELETE_AUTHORIZED",
        "DENY_PATHS_EMPTY",
    ]


def test_a_refused_letter_has_no_warnings() -> None:
    review = _review(
        _letter(authorization__valid_until=answer("2020-01-01"), scope__deny_paths=answer([]))
    )

    assert not review.ready
    assert review.warnings == ()


def _nuclei_attack(**extra: Any) -> dict[str, Any]:
    quote = "A carta autoriza."
    attack: dict[str, Any] = {"nuclei": answer(True, "carta", quote)}
    attack.update({name: answer(value, "carta", quote) for name, value in extra.items()})
    return attack


def _nuclei_codes(review: LetterReview) -> list[tuple[str, str]]:
    return [(w.field, w.code) for w in review.warnings if "nuclei" in w.field]


def test_nuclei_without_writes_or_wide_paths_adds_no_extra_warning() -> None:
    review = _review(_letter(attack=_nuclei_attack(nuclei_login=True)))

    assert _nuclei_codes(review) == []


def test_nuclei_with_the_three_writes_warns_about_writing() -> None:
    attack = _nuclei_attack(
        allow_authz_writes=True, allow_invalid_input_writes=True, allow_upload_scan=True
    )

    review = _review(_letter(attack=attack))

    assert _nuclei_codes(review) == [("attack.nuclei", "NUCLEI_WRITES_AUTHORIZED")]


def test_nuclei_with_only_one_write_does_not_warn_about_nuclei_writing() -> None:
    review = _review(_letter(attack=_nuclei_attack(allow_authz_writes=True)))

    assert _nuclei_codes(review) == []


def test_nuclei_with_wide_paths_warns_that_denied_paths_stay_denied() -> None:
    review = _review(_letter(attack=_nuclei_attack(nuclei_wide_paths=True)))

    (warning,) = (w for w in review.warnings if w.field == "attack.nuclei_wide_paths")
    assert warning.code == "ATTACK_FLAG_AUTHORIZED"
    assert "negados continuam negados" in warning.message
