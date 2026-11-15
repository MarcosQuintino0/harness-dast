"""Aprovação e resumo com `scan.include_outcomes` (ADR 0050)."""

import copy
from typing import Any

import pytest

from harness_dast.domain.errors import ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import check_approval
from harness_dast.domain.scope_approval_summary import describe_protection
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile, valid_profile_data


def _profile(**scan: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data["scan"] = scan
    return ProductProfile.from_data(data)


def test_summary_shows_the_extra_attacked_classes_only_when_the_list_is_not_empty() -> None:
    plain = "\n".join(describe_protection(valid_profile()))
    listed = "\n".join(describe_protection(_profile(include_outcomes=["not_found", "conflict"])))

    assert "ATACA TAMBÉM" not in plain
    assert "ATACA TAMBÉM OPERAÇÕES QUE DERAM: not_found, conflict" in listed


def test_an_approval_made_before_the_field_still_holds_with_the_default_list() -> None:
    approval = approval_for(valid_profile())

    check_approval(_profile(include_outcomes=[]), approval).ensure_approved()


def test_turning_include_outcomes_on_requires_approving_again() -> None:
    approval = approval_for(valid_profile())

    check = check_approval(_profile(include_outcomes=["not_found"]), approval)

    assert check.state == "changed"
    assert check.changed_blocks == ("scan",)
    with pytest.raises(ScopeNotApproved):
        check.ensure_approved()
