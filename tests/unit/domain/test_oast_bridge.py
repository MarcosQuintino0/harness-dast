"""Decisão da ponte de laboratório."""

import pytest

from harness_dast.domain.oast_bridge import should_mount_oast_bridge


@pytest.mark.parametrize(
    ("url", "requested", "expected"),
    [
        ("http://crapi:8888", True, True),
        ("http://crapi:8888", False, False),
        ("http://crapi.example.com", True, False),
        ("http://outro", True, False),
        ("http://[invalid", True, False),
        ("", True, False),
    ],
)
def test_bridge_requires_crapi_and_authorization(url: str, requested: bool, expected: bool) -> None:
    assert should_mount_oast_bridge(url, requested=requested) is expected


def test_unverifiable_state_requires_reason() -> None:
    from pydantic import ValidationError

    from harness_dast.domain.oast_verification import OastVerification

    with pytest.raises(ValidationError):
        OastVerification(zap="unverifiable", ssrf="verifiable")
