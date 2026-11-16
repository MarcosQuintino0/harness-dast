"""Aprovação e resumo com `scan.allow_upload_scan` (ADR 0052)."""

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.errors import ConfigError, ScopeNotApproved
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scope_approval import check_approval
from harness_dast.domain.scope_approval_summary import describe_protection
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests, protected_blocks
from tests.fakes.approvals import approval_for
from tests.fakes.profile_data import valid_profile, valid_profile_data


def _profile(**scan: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data["scan"] = scan
    return ProductProfile.from_data(data)


def _canonical_scan(profile: ProductProfile) -> str:
    return json.dumps(protected_blocks(profile)["scan"], separators=(",", ":"))


@pytest.mark.parametrize("scan", [{}, {"allow_upload_scan": False}])
def test_the_default_leaves_the_key_out_and_keeps_every_digest_of_before(
    scan: dict[str, Any],
) -> None:
    plain = valid_profile()
    profile = _profile(**scan)

    assert "allow_upload_scan" not in _canonical_scan(profile)
    assert block_digests(profile) == block_digests(plain)
    assert combine_digests("demo", block_digests(profile)) == combine_digests(
        "demo", block_digests(plain)
    )


def test_an_approval_made_before_the_field_still_holds_with_the_default() -> None:
    approval = approval_for(valid_profile())

    check_approval(_profile(allow_upload_scan=False), approval).ensure_approved()


def test_turning_the_upload_scan_on_changes_only_the_scan_block_and_requires_approving_again() -> (
    None
):
    approval = approval_for(valid_profile())
    on = _profile(allow_upload_scan=True)

    check = check_approval(on, approval)

    assert '"allow_upload_scan":true' in _canonical_scan(on)
    assert check.state == "changed"
    assert check.changed_blocks == ("scan",)
    with pytest.raises(ScopeNotApproved):
        check.ensure_approved()


def test_an_approval_made_with_the_upload_scan_on_holds_for_the_same_profile() -> None:
    on = _profile(allow_upload_scan=True)

    check_approval(on, approval_for(on)).ensure_approved()


def test_the_summary_shows_the_upload_scan_only_when_it_is_on() -> None:
    plain = "\n".join(describe_protection(valid_profile()))
    listed = "\n".join(describe_protection(_profile(allow_upload_scan=True)))

    assert "ENVIO DE ARQUIVO" not in plain
    assert "VARRE TAMBÉM OPERAÇÕES DE ENVIO DE ARQUIVO (scan.allow_upload_scan)" in listed


@pytest.mark.parametrize("value", ["sim", "true", 1, [True], None])
def test_the_field_must_be_a_real_boolean(value: object) -> None:
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"allow_upload_scan": value})
    with pytest.raises(ConfigError):
        ProductProfile.from_data({**valid_profile_data(), "scan": {"allow_upload_scan": value}})


def test_the_default_is_off() -> None:
    assert ScanConfig().allow_upload_scan is False


def test_pacing_default_preserves_approval_and_proxy_requires_new_approval() -> None:
    original = valid_profile()
    legacy = _profile(pacing="legacy")
    proxy = _profile(pacing="proxy")

    assert block_digests(original) == block_digests(legacy)
    assert block_digests(original)["scan"] != block_digests(proxy)["scan"]
    check_approval(legacy, approval_for(original)).ensure_approved()
    with pytest.raises(ScopeNotApproved):
        check_approval(proxy, approval_for(original)).ensure_approved()
