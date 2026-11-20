"""Permissões do Nuclei derivadas do perfil, sem chave própria de escrita (ADR 0122)."""

from typing import Any

import pytest

from harness_dast.domain.nuclei_permissions import NucleiProfilePermissions, nuclei_permissions
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def _profile(
    *,
    nuclei: bool = True,
    login: bool = False,
    authz: bool = False,
    negative: bool = False,
    upload: bool = False,
    delete: bool = False,
) -> ProductProfile:
    data: dict[str, Any] = valid_profile_data()
    data["extra_checks"] = {"nuclei": nuclei, "nuclei_login": login}
    data["authz"] = {"allow_writes": authz}
    data["negative"] = {"allow_writes": negative}
    data["scan"] = {"allow_upload_scan": upload}
    if delete:
        data["scope"]["allow"][0]["methods"] = ["GET", "POST", "DELETE"]
    return ProductProfile.from_data(data)


def test_permissions_are_all_false_when_the_profile_only_enables_nuclei() -> None:
    assert nuclei_permissions(_profile()) == NucleiProfilePermissions(False, False, False)


@pytest.mark.parametrize("login", [False, True])
def test_login_follows_nuclei_login_when_nuclei_is_on(login: bool) -> None:
    assert nuclei_permissions(_profile(login=login)).login is login


def test_writes_are_allowed_when_the_three_existing_writes_are_on() -> None:
    profile = _profile(authz=True, negative=True, upload=True)

    assert nuclei_permissions(profile) == NucleiProfilePermissions(True, False, False)


@pytest.mark.parametrize(
    ("authz", "negative", "upload"),
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
    ],
)
def test_writes_stay_off_when_only_some_of_the_existing_writes_are_on(
    authz: bool, negative: bool, upload: bool
) -> None:
    profile = _profile(authz=authz, negative=negative, upload=upload, delete=True)

    assert nuclei_permissions(profile).writes is False
    assert nuclei_permissions(profile).delete is False


def test_delete_is_allowed_when_writes_are_on_and_scope_names_delete() -> None:
    profile = _profile(authz=True, negative=True, upload=True, delete=True)

    assert nuclei_permissions(profile) == NucleiProfilePermissions(True, True, False)


def test_delete_stays_off_when_scope_does_not_name_delete() -> None:
    profile = _profile(authz=True, negative=True, upload=True, delete=False)

    assert nuclei_permissions(profile).delete is False


def test_delete_stays_off_when_scope_names_delete_but_writes_are_off() -> None:
    assert nuclei_permissions(_profile(delete=True)).delete is False


def test_permissions_are_all_false_when_nuclei_is_off() -> None:
    profile = _profile(
        nuclei=False, login=True, authz=True, negative=True, upload=True, delete=True
    )

    assert nuclei_permissions(profile) == NucleiProfilePermissions(False, False, False)


def test_permissions_are_all_false_when_the_profile_has_no_extra_checks() -> None:
    data = valid_profile_data()
    data["authz"] = {"allow_writes": True}

    assert nuclei_permissions(ProductProfile.from_data(data)) == (False, False, False)
