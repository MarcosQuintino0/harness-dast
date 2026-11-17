"""Impressão digital: as chaves da V1.12 só mudam o resumo quando ligadas (ADR 0096)."""

import copy
from pathlib import Path
from typing import Any

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests, protected_blocks
from tests.fakes.profile_data import valid_profile_data

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "letter"
# Resumos gerais dos perfis do repositório calculados com o código ANTERIOR à V1.12.
GOLDEN_DIGESTS = {
    "clinica-piloto": "93430c788793ce89c6df74bcb63673626c488899e8318eeee6d2a4c3737d76cb",
    "livraria-exemplo": "e08a67ec82f7062a3992536ec817dcc5858e5a6daf193cc087d2784a7f6a32a6",
}


def _overall(profile: ProductProfile) -> str:
    return combine_digests(profile.product, block_digests(profile))


def _profile(**blocks: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data.update(blocks)
    return ProductProfile.from_data(data)


@pytest.mark.parametrize("name", sorted(GOLDEN_DIGESTS))
def test_an_existing_repository_profile_keeps_its_digest(name: str) -> None:
    text = (GOLDEN / f"{name}.target.golden.yml").read_text(encoding="utf-8")

    profile = ProductProfile.from_data(parse_profile_yaml(text))

    assert _overall(profile) == GOLDEN_DIGESTS[name]
    assert "extra_checks" not in protected_blocks(profile)


@pytest.mark.parametrize(
    "blocks",
    [
        {},
        {"scan": {"pacing": "legacy", "inject_headers": False, "oast": False}},
        {"extra_checks": {}},
        {"extra_checks": {"allow_rate_tests": False, "experimental_rules": False}},
    ],
)
def test_default_values_are_left_out_like_missing_ones(blocks: dict[str, Any]) -> None:
    assert _overall(_profile(**blocks)) == _overall(_profile())


@pytest.mark.parametrize(
    "blocks",
    [
        {"scan": {"pacing": "proxy"}},
        {"scan": {"inject_headers": True}},
        {"scan": {"oast": True}},
        {"extra_checks": {"allow_rate_tests": True}},
        {"extra_checks": {"experimental_rules": True}},
        {"extra_checks": {"inventory": True}},
    ],
)
def test_turning_any_key_on_changes_the_digest_and_the_summary(blocks: dict[str, Any]) -> None:
    base = _profile()
    changed = _profile(**blocks)

    assert _overall(changed) != _overall(base)
    assert describe_protection(changed) != describe_protection(base)


def test_each_extra_check_changes_the_digest_in_its_own_way() -> None:
    digests = {
        _overall(_profile(extra_checks={name: True}))
        for name in ("allow_rate_tests", "experimental_rules", "inventory")
    }

    assert len(digests) == 3
    assert "extra_checks" in block_digests(_profile(extra_checks={"inventory": True}))
