"""`scan.include_outcomes` no perfil: lista fechada de classes, sem repetição (ADR 0050)."""

import copy
from typing import Any

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scan_config import EXTRA_OUTCOMES, ScanConfig
from tests.fakes.profile_data import valid_profile_data


def _load(value: object) -> ProductProfile:
    data = copy.deepcopy(valid_profile_data())
    data["scan"] = {"include_outcomes": value}
    return ProductProfile.from_data(data)


def test_default_is_empty() -> None:
    assert ScanConfig().include_outcomes == ()


@pytest.mark.parametrize("name", sorted(EXTRA_OUTCOMES))
def test_each_extra_class_is_accepted(name: str) -> None:
    assert _load([name]).scan.include_outcomes == (name,)


def test_all_five_classes_together_are_accepted() -> None:
    assert set(_load(sorted(EXTRA_OUTCOMES)).scan.include_outcomes) == EXTRA_OUTCOMES


@pytest.mark.parametrize(
    "value",
    [
        ["auth_error"],
        ["csrf_error"],
        ["rate_limited"],
        ["server_error"],
        ["redirect"],
        ["timeout"],
        ["skipped_denied"],
        ["success"],
        [""],
        ["NOT_FOUND"],
        ["*"],
        ["not_found", "auth_error"],
    ],
)
def test_a_class_outside_the_closed_list_is_refused_with_the_field_path(value: list[str]) -> None:
    with pytest.raises(ConfigError) as caught:
        _load(value)

    assert "scan.include_outcomes" in caught.value.message


@pytest.mark.parametrize("value", ["not_found", None, 3, True, {"a": 1}, [None], [3], [["x"]]])
def test_a_value_that_is_not_a_list_of_texts_is_refused(value: object) -> None:
    with pytest.raises(ConfigError, match=r"scan\.include_outcomes"):
        _load(value)


def test_a_repeated_class_is_refused() -> None:
    with pytest.raises(ConfigError, match="repetida"):
        _load(["not_found", "not_found"])


def test_more_than_five_items_are_refused() -> None:
    with pytest.raises(ConfigError, match=r"scan\.include_outcomes"):
        _load(["not_found"] * 6)


def test_an_unknown_scan_field_is_still_refused() -> None:
    data: dict[str, Any] = copy.deepcopy(valid_profile_data())
    data["scan"] = {"include_outcome": ["not_found"]}

    with pytest.raises(ConfigError):
        ProductProfile.from_data(data)
