"""QA independente (V1.5c): impressão digital da aprovação com as chaves novas (ADR 0050 a 0052).

Oráculo próprio: cada campo que amplia o ataque ou reduz o que se relata, saindo do padrão, muda a
impressão digital; o padrão explícito e a ordem de conjuntos não mudam; perfil antigo mantém.
"""

import copy
import itertools
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harness_dast.domain.negative_values import CLASS_ORDER
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_config import EXTRA_OUTCOMES
from harness_dast.domain.scope_approval import check_approval
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile_data


def _profile(**blocks: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    for name, value in blocks.items():
        data[name] = value
    return ProductProfile.from_data(data)


def _digest(profile: ProductProfile) -> str:
    return combine_digests(profile.product, block_digests(profile))


BASE = _digest(_profile())


@pytest.mark.parametrize(
    "block",
    [
        {"negative": {"allow_writes": True}},
        {"negative": {"max_cases_per_operation": 7}},
        {"negative": {"max_cases_per_operation": 1}},
        {"negative": {"max_requests": 201}},
        {"negative": {"max_requests": 1000}},
        {"negative": {"max_requests": 1}},
        {"negative": {"disabled_classes": ["wrong_type"]}},
        {"scan": {"allow_upload_scan": True}},
        {"scan": {"include_outcomes": ["not_found"]}},
        {"scan": {"include_outcomes": ["logical_failure"]}},
    ],
)
def test_every_new_key_off_its_default_changes_the_digest(block: dict[str, Any]) -> None:
    assert _digest(_profile(**block)) != BASE


def test_each_negative_class_that_is_disabled_changes_the_digest_in_its_own_way() -> None:
    seen = {_digest(_profile(negative={"disabled_classes": [name]})) for name in CLASS_ORDER}

    assert len(seen) == len(CLASS_ORDER)
    assert BASE not in seen


def test_each_extra_outcome_changes_the_digest_in_its_own_way() -> None:
    seen = {_digest(_profile(scan={"include_outcomes": [name]})) for name in EXTRA_OUTCOMES}

    assert len(seen) == len(EXTRA_OUTCOMES)
    assert BASE not in seen


@pytest.mark.parametrize(
    "block",
    [
        {"negative": {}},
        {"negative": {"allow_writes": False}},
        {"negative": {"max_cases_per_operation": 6, "max_requests": 200, "disabled_classes": []}},
        {"scan": {"allow_upload_scan": False}},
        {"scan": {"include_outcomes": []}},
        {"scan": {"include_outcomes": [], "allow_upload_scan": False}},
    ],
)
def test_explicit_defaults_keep_the_digest_so_old_approvals_still_hold(
    block: dict[str, Any],
) -> None:
    profile = _profile(**block)

    assert _digest(profile) == BASE
    check_approval(profile, approval_for(_profile())).ensure_approved()


def test_a_negative_block_equal_to_the_default_is_not_a_block_of_its_own() -> None:
    assert "negative" not in block_digests(_profile(negative={"allow_writes": False}))
    assert "negative" in block_digests(_profile(negative={"allow_writes": True}))


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.sampled_from(CLASS_ORDER), min_size=1, max_size=len(CLASS_ORDER), unique=True),
    st.randoms(use_true_random=False),
)
def test_the_order_of_disabled_classes_never_changes_the_digest(names: list[str], rnd: Any) -> None:
    shuffled = list(names)
    rnd.shuffle(shuffled)

    assert _digest(_profile(negative={"disabled_classes": names})) == _digest(
        _profile(negative={"disabled_classes": shuffled})
    )


def test_the_order_of_include_outcomes_never_changes_the_digest() -> None:
    combos = {
        _digest(_profile(scan={"include_outcomes": list(order)}))
        for order in itertools.permutations(("conflict", "not_found", "client_error"))
    }

    assert len(combos) == 1


def test_a_widened_profile_is_not_approved_by_the_approval_of_the_default_one() -> None:
    approval = approval_for(_profile())

    for block in (
        {"negative": {"allow_writes": True}},
        {"scan": {"allow_upload_scan": True}},
        {"scan": {"include_outcomes": ["not_found"]}},
    ):
        check = check_approval(_profile(**block), approval)
        assert check.state == "changed"
        assert check.changed_blocks


def test_negative_is_reported_as_its_own_changed_block() -> None:
    check = check_approval(_profile(negative={"allow_writes": True}), approval_for(_profile()))

    assert check.changed_blocks == ("negative",)


def test_removing_a_non_default_negative_block_also_requires_approving_again() -> None:
    approval = approval_for(_profile(negative={"allow_writes": True}))

    check = check_approval(_profile(), approval)

    assert check.state == "changed"
    assert check.changed_blocks == ("negative",)


def test_the_digest_does_not_depend_on_the_order_of_keys_in_the_negative_block() -> None:
    first = _profile(negative={"allow_writes": True, "max_requests": 50})
    second = _profile(negative={"max_requests": 50, "allow_writes": True})

    assert _digest(first) == _digest(second)
