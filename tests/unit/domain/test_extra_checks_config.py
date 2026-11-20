"""Perfil: `scan.inject_headers`, `scan.oast` e o bloco `extra_checks` (ADR 0096)."""

import copy
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.extra_checks_config import NUCLEI_FIELDS
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def _load(**blocks: Any) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data.update(blocks)
    return ProductProfile.from_data(data)


def test_a_profile_without_the_keys_has_everything_off() -> None:
    profile = _load()

    assert profile.scan.inject_headers is False
    assert profile.scan.oast is False
    assert profile.scan.pacing == "legacy"
    assert profile.extra_checks.is_default()


def test_the_keys_load_when_present() -> None:
    profile = _load(
        scan={"inject_headers": True, "oast": True, "pacing": "proxy"},
        extra_checks={"allow_rate_tests": True, "inventory": True},
    )

    assert profile.scan.inject_headers
    assert profile.scan.oast
    assert profile.extra_checks.allow_rate_tests
    assert profile.extra_checks.inventory
    assert profile.extra_checks.experimental_rules is False
    assert not profile.extra_checks.is_default()


@pytest.mark.parametrize(
    "blocks",
    [
        {"extra_checks": {"unknown": True}},
        {"extra_checks": {"inventory": "yes"}},
        {"extra_checks": {"allow_rate_tests": 1}},
        {"scan": {"oast": "true"}},
        {"scan": {"inject_headers": 1}},
        {"scan": {"pacing": "fast"}},
    ],
)
def test_unknown_key_wrong_type_or_invalid_value_is_rejected(blocks: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        _load(**blocks)


@pytest.mark.parametrize("name", NUCLEI_FIELDS)
def test_a_nuclei_key_defaults_to_false_when_absent(name: str) -> None:
    assert getattr(_load().extra_checks, name) is False


@pytest.mark.parametrize("name", NUCLEI_FIELDS)
@pytest.mark.parametrize("value", [True, False])
def test_a_nuclei_key_preserves_an_explicit_boolean(name: str, value: bool) -> None:
    assert getattr(_load(extra_checks={name: value}).extra_checks, name) is value


@pytest.mark.parametrize("name", NUCLEI_FIELDS)
@pytest.mark.parametrize("value", ["true", 1, None, {"value": True}])
def test_a_nuclei_key_rejects_an_invalid_value(name: str, value: object) -> None:
    with pytest.raises(ConfigError):
        _load(extra_checks={name: value})
