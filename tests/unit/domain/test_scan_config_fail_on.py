"""`--fail-on` só endurece o limiar do perfil: flags só reduzem."""

import pytest

from harness_dast.domain.scan_config import FailOn, effective_fail_on


@pytest.mark.parametrize(
    ("profile", "requested", "expected"),
    [
        ("none", None, "none"),
        ("high", None, "high"),
        ("high", "none", "high"),  # afrouxar é recusado
        ("high", "medium", "medium"),
        ("high", "low", "low"),
        ("low", "high", "low"),  # o perfil mais rígido vale
        ("none", "medium", "medium"),
        ("medium", "medium", "medium"),
    ],
)
def test_effective_fail_on_never_relaxes_the_profile(
    profile: FailOn, requested: FailOn | None, expected: FailOn
) -> None:
    assert effective_fail_on(profile, requested) == expected
