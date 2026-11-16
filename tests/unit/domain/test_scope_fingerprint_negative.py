"""Impressão digital: o bloco `negative` só entra quando difere do padrão (ADR 0051)."""

import copy
from typing import Any

import pytest

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval import ScopeApproval, check_approval
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import (
    BLOCK_IDS,
    block_digests,
    combine_digests,
    describe_block,
    protected_blocks,
)
from tests.fakes.profile_data import valid_profile_data

# Resumo geral do perfil de teste ANTES do bloco `negative` existir (calculado com o código da
# versão anterior): o perfil que não usa o bloco precisa manter exatamente este valor.
DIGEST_BEFORE_THE_BLOCK = "c279ffb213a1eeaeca1c2ee3231a4a2e1d50da4df12b020b79edb8e79f4f3965"
OLD_BLOCKS = [name for name in BLOCK_IDS if name not in {"negative", "technologies"}]


def profile(**negative: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    if negative:
        data["negative"] = negative
    return ProductProfile.from_data(data)


def overall(item: ProductProfile) -> str:
    return combine_digests(item.product, block_digests(item))


def test_a_profile_without_the_block_keeps_the_exact_digest_it_had_before() -> None:
    item = profile()

    assert overall(item) == DIGEST_BEFORE_THE_BLOCK
    assert sorted(block_digests(item)) == sorted(OLD_BLOCKS)
    assert "negative" not in protected_blocks(item)


@pytest.mark.parametrize(
    "block",
    [
        {},
        {"allow_writes": False, "max_cases_per_operation": 6, "max_requests": 200},
        {"disabled_classes": []},
    ],
)
def test_a_block_equal_to_the_default_is_left_out_like_a_missing_one(block: dict[str, Any]) -> None:
    data = copy.deepcopy(valid_profile_data())
    data["negative"] = block

    item = ProductProfile.from_data(data)

    assert overall(item) == DIGEST_BEFORE_THE_BLOCK
    assert "negative" not in block_digests(item)


@pytest.mark.parametrize(
    "change",
    [
        {"allow_writes": True},
        {"max_requests": 100},
        {"max_requests": 201},
        {"max_cases_per_operation": 5},
        {"disabled_classes": ["too_long"]},
    ],
)
def test_any_change_adds_the_block_and_moves_only_the_overall_digest_and_its_own(
    change: dict[str, Any],
) -> None:
    base = block_digests(profile())
    changed = block_digests(profile(**change))

    assert set(changed) - set(base) == {"negative"}
    assert {name: changed[name] for name in base} == base
    assert overall(profile(**change)) != DIGEST_BEFORE_THE_BLOCK


def test_each_change_gives_its_own_digest() -> None:
    digests = {
        block_digests(profile(**change))["negative"]
        for change in (
            {"allow_writes": True},
            {"max_requests": 100},
            {"max_cases_per_operation": 5},
            {"disabled_classes": ["too_long"]},
        )
    }

    assert len(digests) == 4


def test_the_order_of_the_disabled_classes_does_not_count() -> None:
    first = profile(disabled_classes=["too_long", "wrong_type"])
    second = profile(disabled_classes=["wrong_type", "too_long"])

    assert block_digests(first)["negative"] == block_digests(second)["negative"]


def test_going_back_to_the_default_goes_back_to_the_original_digest() -> None:
    assert overall(profile(allow_writes=True)) != DIGEST_BEFORE_THE_BLOCK
    assert overall(profile(allow_writes=False)) == DIGEST_BEFORE_THE_BLOCK


def test_an_approval_made_before_the_block_existed_is_still_approved() -> None:
    item = profile()
    old = {name: digest for name, digest in block_digests(item).items() if name in OLD_BLOCKS}
    approval = ScopeApproval(
        schema_version=2,
        product=item.product,
        digest=DIGEST_BEFORE_THE_BLOCK,
        blocks=old,
        approved_at="2026-11-01T00:00:00+00:00",
        summary=("resumo",),
    )

    assert check_approval(item, approval).state == "approved"


def test_turning_the_block_on_after_the_approval_names_it_as_changed() -> None:
    item = profile()
    approval = ScopeApproval(
        schema_version=2,
        product=item.product,
        digest=DIGEST_BEFORE_THE_BLOCK,
        blocks=block_digests(item),
        approved_at="2026-11-01T00:00:00+00:00",
        summary=("resumo",),
    )

    check = check_approval(profile(allow_writes=True), approval)

    assert check.state == "changed"
    assert check.changed_blocks == ("negative",)
    assert describe_block("negative") == "teste de valores que o esquema proíbe"


def test_the_summary_shows_nothing_by_default_and_the_numbers_and_the_write_warning_otherwise() -> (
    None
):
    assert not [line for line in describe_protection(profile()) if "INVÁLIDOS" in line]

    lines = describe_protection(
        profile(
            allow_writes=True,
            max_requests=120,
            max_cases_per_operation=4,
            disabled_classes=["too_long"],
        )
    )

    assert "VALORES INVÁLIDOS: até 120 pedidos, 4 por operação (negative)" in lines
    assert any("ESCRITA DE VALOR INVÁLIDO AUTORIZADA" in line for line in lines)
    assert any("classes desligadas: too_long" in line for line in lines)


def test_without_writes_the_summary_has_no_write_line() -> None:
    lines = describe_protection(profile(max_requests=50))

    assert any("VALORES INVÁLIDOS" in line for line in lines)
    assert not any("ESCRITA DE VALOR INVÁLIDO" in line for line in lines)
