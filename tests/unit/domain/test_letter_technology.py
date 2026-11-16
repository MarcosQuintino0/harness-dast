"""Contrato consultivo das tecnologias declaradas."""

from datetime import date
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import LetterReview, review_letter
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import check_approval
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests
from tests.fakes.approvals import approval_for
from tests.fakes.letter_data import answer, valid_letter_data
from tests.fakes.profile_data import valid_profile_data


def review(value: dict[str, Any] | None) -> LetterReview:
    data = valid_letter_data()
    if value is not None:
        data["attack"] = {"technologies": value}
    return review_letter(Letter.from_data(data), "demo", date(2026, 11, 14))


def test_letter_copies_quoted_declaration_and_warns() -> None:
    result = review(answer(["h2"], "carta", "Banco H2."))
    assert result.ready
    assert result.profile_text is not None
    assert "technologies" in result.blocks
    assert '"Banco H2."' in result.profile_text
    warning = next(w for w in result.warnings if w.code == "TECHNOLOGIES_ADVISORY")
    assert "não confirma" in warning.message
    assert "nem reduz" in warning.message


@pytest.mark.parametrize("value", [None, {"source": "desconhecido"}, answer([], "pessoa")])
def test_empty_or_unknown_does_not_generate_declaration(value: dict[str, Any] | None) -> None:
    result = review(value)
    assert result.ready
    assert "technologies" not in result.blocks


@pytest.mark.parametrize(
    "value",
    [answer(["h2"], "pessoa", "Banco H2."), answer(["h2"], "carta"), answer(["h2"], "carta", "  ")],
)
def test_declaration_requires_letter_and_quote(value: dict[str, Any]) -> None:
    result = review(value)
    assert not result.ready
    assert any(i.code == "TECHNOLOGIES_NEED_LETTER" for i in result.issues)


@pytest.mark.parametrize("value", ["h2", [1], ["H2"], ["h2", "h2"], ["bad name"]])
def test_malformed_declaration_is_rejected(value: object) -> None:
    result = review(answer(value, "carta", "Banco H2."))
    assert not result.ready
    assert any(i.code == "INVALID_VALUE" for i in result.issues)


def test_declaration_changes_approval_and_is_visible() -> None:
    data = valid_profile_data()
    old = ProductProfile.from_data(data)
    data["technologies"] = {"value": ["h2"], "source": "carta", "quote": "Banco H2."}
    new = ProductProfile.from_data(data)
    assert combine_digests(old.product, block_digests(old)) != combine_digests(
        new.product, block_digests(new)
    )
    assert set(block_digests(new)) - set(block_digests(old)) == {"technologies"}
    summary = " ".join(describe_protection(new))
    assert "h2" in summary
    assert "Banco H2." in summary
    assert "não confirma" in summary


@pytest.mark.parametrize(
    "declaration",
    [
        {"value": ["h2"], "source": "pessoa", "quote": "Banco H2."},
        {"value": ["h2"], "source": "carta"},
        {"value": [], "source": "carta", "quote": "Banco H2."},
    ],
)
def test_profile_rejects_declaration_without_authority(declaration: dict[str, object]) -> None:
    data = valid_profile_data()
    data["technologies"] = declaration
    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)


def test_approval_changes_when_declaration_is_added_or_edited() -> None:
    data = valid_profile_data()
    old = ProductProfile.from_data(data)
    approval = approval_for(old)
    data["technologies"] = None
    assert check_approval(ProductProfile.from_data(data), approval).state == "approved"
    data["technologies"] = {"value": ["h2"], "source": "carta", "quote": "Banco H2."}
    declared = ProductProfile.from_data(data)
    changed = check_approval(declared, approval)
    assert changed.state == "changed"
    assert changed.changed_blocks == ("technologies",)
    approval = approval_for(declared)
    data["technologies"]["quote"] = "Usamos H2."
    assert check_approval(ProductProfile.from_data(data), approval).changed_blocks == (
        "technologies",
    )


def test_pacing_and_technology_change_only_their_approval_blocks() -> None:
    data = valid_profile_data()
    old = ProductProfile.from_data(data)
    approval = approval_for(old)
    data["scan"] = {"pacing": "legacy"}
    legacy = ProductProfile.from_data(data)
    assert check_approval(legacy, approval).state == "approved"
    data["scan"] = {"pacing": "proxy"}
    proxy = ProductProfile.from_data(data)
    assert check_approval(proxy, approval).changed_blocks == ("scan",)
    data["technologies"] = {"value": ["h2"], "source": "carta", "quote": "Banco H2."}
    combined = ProductProfile.from_data(data)
    assert check_approval(combined, approval).changed_blocks == ("technologies", "scan")
    assert combined.scan == proxy.scan
