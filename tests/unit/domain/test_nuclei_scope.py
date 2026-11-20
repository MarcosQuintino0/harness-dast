import itertools
from typing import Any

import pytest

from harness_dast.domain.errors import ScopeViolation
from harness_dast.domain.nuclei_manifest import NucleiPermissions
from harness_dast.domain.nuclei_scope import build_nuclei_scope
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import OutboundRequest, ScopeGuard
from harness_dast.domain.wide_guard import WideScopeGuard
from tests.fakes.profile_data import valid_profile_data

_HOST = "api.hml.acme-teste.net.br"
_ALL_PERMISSIONS = [
    NucleiPermissions(writes=w, delete=d) for w, d in itertools.product([False, True], repeat=2)
]


def _profile(*extra_rules: dict[str, Any]) -> ProductProfile:
    """Perfil válido (a regra do host base fica) mais as regras extras."""
    data = valid_profile_data()
    data["scope"]["allow"] = [*data["scope"]["allow"], *extra_rules]
    return ProductProfile.from_data(data)


def _allowed(guard: ScopeGuard, method: str, url: str) -> bool:
    try:
        guard.ensure_allowed(OutboundRequest(method=method, url=url))
    except ScopeViolation:
        return False
    return True


def test_never_adds_an_origin_quando_wide_paths_is_on() -> None:
    profile = _profile(
        {"host": _HOST, "paths": ["/v2/**"], "methods": ["POST"]},
        {"host": "outro.acme-teste.net.br", "paths": ["/**"], "methods": ["GET"]},
    )

    nuclei = build_nuclei_scope(profile, NucleiPermissions(), wide_paths=True)

    assert [r.host for r in nuclei.scope.allow] == [_HOST, "outro.acme-teste.net.br"]
    guard = ScopeGuard(nuclei.scope)
    assert not _allowed(guard, "GET", "https://intruso.acme-teste.net.br/x")
    assert not _allowed(guard, "GET", f"http://{_HOST}/x")
    assert not _allowed(guard, "GET", f"https://{_HOST}:8443/x")


def test_deny_paths_win_quando_wide_paths_is_on() -> None:
    nuclei = build_nuclei_scope(_profile(), NucleiPermissions(), wide_paths=True)
    guard = ScopeGuard(nuclei.scope)

    assert nuclei.scope.deny_paths == ("/api/admin/**",)
    assert not _allowed(guard, "GET", f"https://{_HOST}/api/admin/users")
    assert _allowed(guard, "GET", f"https://{_HOST}/actuator/env")


def test_allows_any_path_and_sets_wide_mode_quando_wide_paths_is_on() -> None:
    nuclei = build_nuclei_scope(_profile(), NucleiPermissions(), wide_paths=True)

    assert nuclei.path_mode == "wide"
    assert all(rule.paths == ("/**",) for rule in nuclei.scope.allow)


def test_keeps_paths_and_strict_mode_quando_wide_paths_is_off() -> None:
    nuclei = build_nuclei_scope(_profile(), NucleiPermissions(), wide_paths=False)
    guard = ScopeGuard(nuclei.scope)

    assert nuclei.path_mode == "strict"
    assert nuclei.scope.allow[0].paths == ("/api/**",)
    assert _allowed(guard, "GET", f"https://{_HOST}/api/contas")
    assert not _allowed(guard, "GET", f"https://{_HOST}/actuator/env")


@pytest.mark.parametrize("wide_paths", [False, True])
@pytest.mark.parametrize(
    ("permissions", "allowed"),
    [
        (NucleiPermissions(), {"GET", "HEAD", "OPTIONS"}),
        (NucleiPermissions(writes=True), {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"}),
        (NucleiPermissions(delete=True), {"GET", "HEAD", "OPTIONS", "DELETE"}),
    ],
)
def test_limits_methods_by_permission_quando_scope_is_built(
    permissions: NucleiPermissions, allowed: set[str], *, wide_paths: bool
) -> None:
    nuclei = build_nuclei_scope(_profile(), permissions, wide_paths=wide_paths)
    guard = ScopeGuard(nuclei.scope)
    every = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}

    got = {m for m in every if _allowed(guard, m, f"https://{_HOST}/api/contas")}

    assert got == allowed


_LOCAL_RULE = {
    "host": "localhost",
    "paths": ["/a"],
    "methods": ["GET"],
    "allow_local": True,
    "scheme": "http",
}


@pytest.mark.parametrize("wide_paths", [False, True])
@pytest.mark.parametrize("permissions", _ALL_PERMISSIONS)
@pytest.mark.parametrize(
    "extra_rules",
    [
        [],
        [{"host": _HOST, "paths": ["/a"], "methods": ["GET"], "port": 8443}],
        [_LOCAL_RULE],
    ],
)
def test_only_narrows_or_equals_quando_deriving_from_any_profile(
    extra_rules: list[dict[str, Any]], permissions: NucleiPermissions, *, wide_paths: bool
) -> None:
    profile = _profile(*extra_rules)

    nuclei = build_nuclei_scope(profile, permissions, wide_paths=wide_paths)

    origin = {(r.host, r.scheme, r.port, r.allow_local) for r in profile.scope.allow}
    derived = {(r.host, r.scheme, r.port, r.allow_local) for r in nuclei.scope.allow}
    assert derived <= origin
    assert nuclei.scope.deny_paths == profile.scope.deny_paths
    assert nuclei.limits == profile.limits
    assert nuclei.windows == profile.scope.windows


@pytest.mark.parametrize(
    "path", ["/api/admin/users", "/API/Admin/users", "/api/x/..%2fadmin/users", "/api/;a/admin/x"]
)
def test_wide_guard_denies_deny_paths_quando_the_nuclei_scope_is_wide(path: str) -> None:
    nuclei = build_nuclei_scope(_profile(), NucleiPermissions(), wide_paths=True)
    guard = WideScopeGuard(nuclei.scope)

    with pytest.raises(ScopeViolation):
        guard.ensure_allowed(OutboundRequest(method="GET", url=f"https://{_HOST}{path}"))


def test_wide_guard_allows_a_path_outside_the_swagger_quando_the_nuclei_scope_is_wide() -> None:
    nuclei = build_nuclei_scope(_profile(), NucleiPermissions(), wide_paths=True)

    outcome = WideScopeGuard(nuclei.scope).ensure_allowed(
        OutboundRequest(method="GET", url=f"https://{_HOST}/actuator/env")
    )

    assert outcome.leaves_allow is False
