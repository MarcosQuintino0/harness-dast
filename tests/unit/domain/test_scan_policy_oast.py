"""Política com e sem `scan.oast`: desligada é idêntica à de antes (ADR 0099)."""

from harness_dast.domain.experimental_rules import EXPERIMENTAL_RULES
from harness_dast.domain.scan_config import ScanConfig
from harness_dast.domain.scan_policy import (
    DEFAULT_DISABLED_RULES,
    OAST_RULES,
    build_policy,
    without_oast,
)

LOG4SHELL = 40043


def test_without_oast_the_policy_is_the_same_as_before() -> None:
    policy = build_policy(ScanConfig())

    assert policy.oast is False
    assert policy.oast_rules == ()
    expected = {rule.plugin_id for rule in DEFAULT_DISABLED_RULES}
    assert set(policy.disabled_rules) == expected | {r.plugin_id for r in EXPERIMENTAL_RULES}
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


def test_reducao_preserva_politica_estreitada_por_estrategia() -> None:
    base = build_policy(ScanConfig(oast=True), experimental_rules=True)
    narrowed = base.model_copy(
        update={
            "disabled_rules": (*base.disabled_rules, 90001, 40033),
            "experimental_rules": tuple(rule for rule in base.experimental_rules if rule != 40033),
            "strength": "LOW",
        }
    )

    reduced = without_oast(narrowed)

    assert {90001, 40033, 40046, 40043, 90023, 90036} <= set(reduced.disabled_rules)
    assert 40046 not in reduced.experimental_rules
    assert reduced.strength == "LOW"
    assert reduced.oast is False
    assert reduced.oast_rules == ()
    assert reduced.url_path_injection == narrowed.url_path_injection
