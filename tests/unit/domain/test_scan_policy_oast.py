"""Política com e sem `scan.oast`: desligada é idêntica à de antes (ADR 0099)."""

from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_policy import (
    DEFAULT_DISABLED_RULES,
    OAST_RULES,
    build_policy,
)

LOG4SHELL = 40043


def test_without_oast_the_policy_is_the_same_as_before() -> None:
    policy = build_policy(ScanConfig())

    assert policy.oast is False
    assert policy.oast_rules == ()
    assert set(policy.disabled_rules) == {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}
    assert LOG4SHELL in policy.disabled_rules
    assert policy.injectable_mask == 51


def test_with_oast_the_rules_that_depend_on_the_return_are_on_and_log4shell_is_not_disabled() -> (
    None
):
    policy = build_policy(ScanConfig(oast=True))

    assert policy.oast is True
    assert policy.oast_rules == tuple(rule.plugin_id for rule in OAST_RULES)
    assert LOG4SHELL not in policy.disabled_rules
    other = {rule.plugin_id for rule in DEFAULT_DISABLED_RULES} - {LOG4SHELL}
    assert other <= set(policy.disabled_rules)


def test_with_oast_the_profile_can_still_decline_one_of_the_rules() -> None:
    policy = build_policy(ScanConfig(oast=True, disable_rules=(90023,)))

    assert 90023 not in policy.oast_rules
    assert 90023 in policy.disabled_rules
    assert 40043 in policy.oast_rules


def test_oast_does_not_change_the_other_policy_fields() -> None:
    base = build_policy(ScanConfig())
    with_oast = build_policy(ScanConfig(oast=True))

    assert (base.strength, base.threshold, base.injectable_mask) == (
        with_oast.strength,
        with_oast.threshold,
        with_oast.injectable_mask,
    )
