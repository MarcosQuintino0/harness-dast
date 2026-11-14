"""QA independente da V1.4: a impressão digital precisa mudar com tudo que amplia o `authz`."""

import copy
from typing import Any

import pytest

from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests
from tests.fakes.profile_data import valid_profile_data

MATRIX = [{"operation": "ler", "allow": ["usuario"], "deny": ["admin"]}]


def _digest(authz: dict[str, Any] | None) -> str:
    data = copy.deepcopy(valid_profile_data())
    if authz is not None:
        data["authz"] = authz
    profile = ProductProfile.from_data(data)
    return combine_digests(profile.product, block_digests(profile))


BASE = _digest(None)


@pytest.mark.parametrize(
    "authz",
    [
        {"allow_writes": True},
        {"derive_mass_candidates": False},
        {"max_derived_candidates": 7},
        {"max_derived_candidates": 20},
        {"mass_assignment_methods": ["PATCH"]},
        {"mass_assignment_methods": ["POST"]},
        {"id_parameters": ["cpf"]},
        {"id_parameters": ["cpf", "matricula"]},
        {"access_matrix": MATRIX},
        {"access_matrix": [{"operation": "ler", "allow": [], "deny": []}]},
        {"access_matrix": [{"operation": "ler", "allow": ["usuario"]}]},
        {"vertical_methods": ["GET", "HEAD", "PUT"]},
        {"disabled_checks": ["horizontal_write"]},
        {"disabled_checks": ["access_matrix"]},
        {"mass_assignment_fields": []},
    ],
)
def test_digest_changes_when_authz_key_leaves_the_default(authz: dict[str, Any]) -> None:
    assert _digest(authz) != BASE


@pytest.mark.parametrize(
    "authz",
    [
        {},
        {"allow_writes": False},
        {"derive_mass_candidates": True, "max_derived_candidates": 6},
        {"mass_assignment_methods": ["PUT", "POST", "PATCH"]},
        {"id_parameters": []},
        {"access_matrix": []},
        {"vertical_methods": ["HEAD", "GET"]},
    ],
)
def test_digest_stays_when_authz_keys_are_explicit_defaults(authz: dict[str, Any]) -> None:
    assert _digest(authz) == BASE


def test_digest_stays_when_matrix_rules_and_roles_are_reordered() -> None:
    first = [
        {"operation": "a", "allow": ["x", "y"], "deny": ["z", "w"]},
        {"operation": "b", "allow": [], "deny": ["x"]},
    ]
    second = [
        {"operation": "b", "allow": [], "deny": ["x"]},
        {"operation": "a", "allow": ["y", "x"], "deny": ["w", "z"]},
    ]

    assert _digest({"access_matrix": first}) == _digest({"access_matrix": second})


@pytest.mark.xfail(strict=True, reason="QA V1.4: id_parameters é conjunto e a ordem muda a digital")
def test_digest_stays_when_id_parameters_are_reordered() -> None:
    assert _digest({"id_parameters": ["cpf", "matricula"]}) == _digest(
        {"id_parameters": ["matricula", "cpf"]}
    )


def test_digest_changes_when_matrix_moves_a_role_from_deny_to_allow() -> None:
    deny = [{"operation": "a", "allow": [], "deny": ["x"]}]
    allow = [{"operation": "a", "allow": ["x"], "deny": []}]

    assert _digest({"access_matrix": deny}) != _digest({"access_matrix": allow})
