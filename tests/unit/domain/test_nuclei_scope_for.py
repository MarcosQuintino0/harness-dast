from typing import Any

from harness_dast.domain.nuclei_scope import nuclei_scope_for
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data


def _profile(extra_checks: dict[str, Any] | None = None, **sections: Any) -> ProductProfile:
    data = valid_profile_data()
    if extra_checks is not None:
        data["extra_checks"] = extra_checks
    data.update(sections)
    return ProductProfile.from_data(data)


def test_scope_for_devolve_none_com_o_nuclei_desligado() -> None:
    assert nuclei_scope_for(_profile()) is None
    assert nuclei_scope_for(_profile({"nuclei": False, "nuclei_wide_paths": True})) is None


def test_scope_for_so_le_com_o_nuclei_ligado_sem_escrita() -> None:
    scope = nuclei_scope_for(_profile({"nuclei": True}))

    assert scope is not None
    assert scope.path_mode == "strict"
    assert all(set(rule.methods) == {"GET", "HEAD", "OPTIONS"} for rule in scope.scope.allow)


def test_scope_for_libera_escrita_com_as_tres_permissoes_do_perfil() -> None:
    scope = nuclei_scope_for(
        _profile(
            {"nuclei": True},
            authz={"allow_writes": True},
            negative={"allow_writes": True},
            scan={"allow_upload_scan": True},
        )
    )

    assert scope is not None
    methods = {method for rule in scope.scope.allow for method in rule.methods}
    assert {"POST", "PUT", "PATCH"} <= methods
    assert "DELETE" not in methods


def test_scope_for_so_usa_caminhos_amplos_com_nuclei_wide_paths() -> None:
    wide = nuclei_scope_for(_profile({"nuclei": True, "nuclei_wide_paths": True}))
    strict = nuclei_scope_for(_profile({"nuclei": True}))

    assert wide is not None
    assert strict is not None
    assert wide.path_mode == "wide"
    assert strict.path_mode == "strict"
