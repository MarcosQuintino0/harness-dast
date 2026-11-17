"""Catálogo de regras alpha e beta da imagem do harness e política com e sem a chave (ADR 0103)."""

import pytest

from harness_dast.domain.experimental_rules import (
    EXPERIMENTAL_RULES,
    enabled_experimental_ids,
    experimental_rule,
    is_experimental_plugin,
)
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_policy import DEFAULT_DISABLED_RULES, build_policy

NOSQL = 40033
NOSQL_TIME = 90039
SSRF = 40046
SELECTED = {NOSQL, NOSQL_TIME, SSRF}


def test_the_catalog_has_the_26_image_rules_with_unique_ids() -> None:
    ids = [rule.plugin_id for rule in EXPERIMENTAL_RULES]

    assert len(ids) == 26
    assert len(set(ids)) == 26


def test_the_selected_list_is_small_fixed_and_only_the_ssrf_needs_the_return() -> None:
    selected = {rule.plugin_id for rule in EXPERIMENTAL_RULES if rule.selected}
    needs_return = {rule.plugin_id for rule in EXPERIMENTAL_RULES if rule.needs_oast}

    assert selected == SELECTED
    assert needs_return == {SSRF}
    assert {rule.quality for rule in EXPERIMENTAL_RULES} == {"alpha", "beta"}


def test_the_catalog_never_overlaps_the_default_disabled_rules() -> None:
    default = {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}

    assert not default & {rule.plugin_id for rule in EXPERIMENTAL_RULES}


@pytest.mark.parametrize(("plugin", "expected"), [("40033", True), ("40018", False), ("x", False)])
def test_a_plugin_is_experimental_only_when_it_is_in_the_catalog(
    plugin: str, expected: bool
) -> None:
    assert is_experimental_plugin(plugin) is expected


def test_the_lookup_accepts_text_and_number_and_ignores_garbage() -> None:
    assert experimental_rule("40033") == experimental_rule(40033)
    assert experimental_rule("") is None
    assert experimental_rule("40033; drop") is None


def test_without_the_key_no_experimental_rule_is_enabled() -> None:
    assert enabled_experimental_ids(experimental=False, oast=True) == ()


def test_with_the_key_the_ssrf_rule_waits_for_the_return() -> None:
    assert set(enabled_experimental_ids(experimental=True, oast=False)) == {NOSQL, NOSQL_TIME}
    assert set(enabled_experimental_ids(experimental=True, oast=True)) == SELECTED


def test_without_the_key_the_effective_policy_is_the_same_as_before() -> None:
    policy = build_policy(ScanConfig())

    assert policy.experimental_rules == ()
    default = {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}
    assert set(policy.disabled_rules) == default | {r.plugin_id for r in EXPERIMENTAL_RULES}


def test_with_the_key_only_the_selected_rules_are_left_on_and_the_rest_stays_off() -> None:
    policy = build_policy(ScanConfig(), experimental_rules=True)

    assert set(policy.experimental_rules) == {NOSQL, NOSQL_TIME}
    off = {rule.plugin_id for rule in EXPERIMENTAL_RULES} - {NOSQL, NOSQL_TIME}
    assert off <= set(policy.disabled_rules)
    assert not {NOSQL, NOSQL_TIME} & set(policy.disabled_rules)
    assert SSRF in policy.disabled_rules


def test_with_the_key_and_oast_the_ssrf_rule_is_on_too() -> None:
    policy = build_policy(ScanConfig(oast=True), experimental_rules=True)

    assert set(policy.experimental_rules) == SELECTED
    assert SSRF not in policy.disabled_rules


def test_the_profile_can_still_decline_a_selected_rule() -> None:
    policy = build_policy(ScanConfig(disable_rules=(NOSQL,)), experimental_rules=True)

    assert NOSQL not in policy.experimental_rules
    assert NOSQL in policy.disabled_rules


def test_the_key_does_not_change_the_other_policy_fields() -> None:
    base = build_policy(ScanConfig())
    on = build_policy(ScanConfig(), experimental_rules=True)

    assert (base.strength, base.threshold, base.injectable_mask, base.oast) == (
        on.strength,
        on.threshold,
        on.injectable_mask,
        on.oast,
    )
