"""QA independente da V1.4: o bloco `authz` recusa tipo errado, nome hostil e valor enorme."""

from typing import Any

import pytest
from pydantic import ValidationError

from harness_dast.domain.authz_config import AuthzConfig


@pytest.mark.parametrize(
    "data",
    [
        {"allow_writes": "true"},
        {"allow_writes": 1},
        {"allow_writes": "yes"},
        {"allow_writes": None},
        {"allow_writes": []},
        {"derive_mass_candidates": "false"},
        {"max_derived_candidates": True},
        {"max_derived_candidates": 0},
        {"max_derived_candidates": 21},
        {"max_derived_candidates": 2.5},
        {"max_derived_candidates": "7"},
        {"mass_assignment_methods": []},
        {"mass_assignment_methods": ["DELETE"]},
        {"mass_assignment_methods": ["post"]},
        {"mass_assignment_methods": "POST"},
        {"vertical_methods": ["DELETE"]},
        {"vertical_methods": ["GET", "OPTIONS"]},
        {"vertical_methods": []},
        {"id_parameters": ["cpf\n"]},
        {"id_parameters": ["cpf", "cpf"]},
        {"id_parameters": ["1cpf"]},
        {"id_parameters": ["cão"]},
        {"id_parameters": ["a" * 65]},
        {"id_parameters": [f"p{i}" for i in range(21)]},
        {"id_parameters": [1]},
        {"id_parameters": "cpf"},
        {"access_matrix": [{"operation": "", "allow": []}]},
        {"access_matrix": [{"operation": "a" * 201}]},
        {"access_matrix": [{"operation": "a", "allow": ["x"], "deny": ["x"]}]},
        {"access_matrix": [{"operation": "a", "allow": ["x", "x"]}]},
        {"access_matrix": [{"operation": "a", "allow": ["x y"]}]},
        {"access_matrix": [{"operation": "a", "allow": ["x" + chr(0xA0) + "y"]}]},
        {"access_matrix": [{"operation": "a", "allow": [f"r{i}" for i in range(21)]}]},
        {"access_matrix": [{"operation": "a"}, {"operation": "a"}]},
        {"access_matrix": [{"operation": f"o{i}"} for i in range(501)]},
        {"access_matrix": [{"operation": "a", "extra": 1}]},
        {"access_matrix": [{"operation": 1}]},
        {"access_matrix": {"operation": "a"}},
        {"unknown_key": True},
        {"disabled_checks": ["nope"]},
    ],
)
def test_authz_config_refuses_malformed_or_hostile_values(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AuthzConfig.model_validate(data)


def test_authz_config_defaults_never_write() -> None:
    config = AuthzConfig()

    assert config.allow_writes is False
    assert config.effective_vertical_methods() <= {"GET", "HEAD"}
    assert "DELETE" not in config.vertical_methods
    assert "DELETE" not in config.mass_assignment_methods


@pytest.mark.parametrize("methods", [["GET", "POST", "PUT", "PATCH"], ["PATCH"], ["HEAD", "PUT"]])
def test_effective_vertical_methods_keep_only_reads_without_allow_writes(
    methods: list[str],
) -> None:
    config = AuthzConfig(vertical_methods=tuple(methods))

    assert config.effective_vertical_methods() <= {"GET", "HEAD"}
