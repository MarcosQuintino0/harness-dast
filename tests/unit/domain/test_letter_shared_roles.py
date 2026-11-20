"""Contrato de papéis compartilhados da carta."""

from datetime import date
from typing import Any

import pytest

from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from tests.fakes.letter_data import answer, valid_letter_data


def review(value: dict[str, Any] | None) -> LetterReview:
    data = valid_letter_data()
    if value is not None:
        data["attack"] = {"authz_shared_roles": value}
    return review_letter(Letter.from_data(data), "demo", date(2026, 11, 14))


def test_letter_generates_shared_roles_from_quoted_authorization() -> None:
    data = valid_letter_data()
    role = data["auth"]["accounts"]["value"][0]["role"]
    result = review(answer([role], "carta", "As contas compartilham os recursos."))
    assert result.ready
    assert "authz.shared_roles" in result.blocks
    assert result.profile_text is not None
    assert "shared_roles:" in result.profile_text


@pytest.mark.parametrize(
    "value", [None, {"source": "desconhecido"}, answer(None, "pessoa"), answer([], "pessoa")]
)
def test_empty_answers_preserve_default(value: dict[str, Any] | None) -> None:
    result = review(value)
    assert result.ready
    assert "authz.shared_roles" not in result.blocks


@pytest.mark.parametrize(
    "value",
    [
        answer(["usuario"], "pessoa", "texto"),
        answer(["usuario"], "carta"),
        answer(["usuario"], "carta", "  "),
    ],
)
def test_populated_answer_requires_letter_and_quote(value: dict[str, Any]) -> None:
    result = review(value)
    assert any(issue.code == "SHARED_ROLES_NEEDS_LETTER" for issue in result.issues)
    assert result.profile_text is None


@pytest.mark.parametrize("value", ["usuario", ["usuario", "usuario"], ["bad role"], [1]])
def test_malformed_roles_are_rejected(value: object) -> None:
    result = review(answer(value, "carta", "texto"))
    assert any(issue.code == "INVALID_VALUE" for issue in result.issues)
    assert result.profile_text is None


def test_unknown_role_is_rejected_by_the_generated_profile() -> None:
    result = review(answer(["inexistente"], "carta", "texto"))
    assert not result.ready
    assert any(issue.code == "PROFILE_REJECTED" for issue in result.issues)
