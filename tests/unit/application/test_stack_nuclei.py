"""`stack up` publica a política da segunda cerca: a do Nuclei ou a que nega tudo (ADR 0122)."""

from pathlib import Path
from typing import Any

from harness_dast.application.stack import BASE_SERVICES, StackUpRequest
from harness_dast.domain.nuclei_scope import NucleiScope
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile_data
from tests.fakes.stack import FakeStopper
from tests.unit.application.test_stack import Rig


def _profile(**extra: Any) -> ProductProfile:
    data = valid_profile_data("demo")
    data["extra_checks"] = {"nuclei": True, **extra.pop("extra_checks", {})}
    data["scope"]["deny_paths"] = ["/api/admin/**", "/api/interno/**"]
    for key, value in extra.items():
        data[key] = value
    return ProductProfile.from_data(data)


def _published(rig: Rig) -> NucleiScope | None:
    ((_, _, _, scope),) = rig.policies.published_nuclei
    return scope


def test_up_sem_nuclei_publica_a_politica_que_nega_tudo(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.manager.up(StackUpRequest(product="demo"))

    assert _published(rig) is None
    state = rig.states.state
    assert state is not None
    assert state.nuclei_policy_dir is not None
    assert rig.policies.published_nuclei[0][2] == state.nuclei_policy_dir
    assert state.nuclei_policy_dir != state.policy_dir
    assert state.nuclei_audit_dir != state.audit_dir


def test_up_com_nuclei_publica_o_escopo_derivado_do_perfil(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    profile = _profile()
    rig.profiles.add(profile)

    rig.manager.up(StackUpRequest(product="demo"))

    scope = _published(rig)
    assert scope is not None
    assert scope.path_mode == "strict"
    assert [rule.host for rule in scope.scope.allow] == [rule.host for rule in profile.scope.allow]
    assert scope.limits == profile.limits


def test_up_com_nuclei_preserva_deny_paths_e_origens_do_perfil(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    profile = _profile(extra_checks={"nuclei_wide_paths": True})
    rig.profiles.add(profile)

    rig.manager.up(StackUpRequest(product="demo"))

    scope = _published(rig)
    assert scope is not None
    assert scope.path_mode == "wide"
    assert scope.scope.deny_paths == profile.scope.to_scope().deny_paths
    origins = {(r.host, r.scheme, r.port) for r in scope.scope.allow}
    assert origins == {(r.host, r.scheme, r.port) for r in profile.scope.allow}


def test_a_politica_do_zap_continua_a_do_perfil_com_o_nuclei_ligado(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.profiles.add(_profile(extra_checks={"nuclei_wide_paths": True}))

    rig.manager.up(StackUpRequest(product="demo"))

    state = rig.states.state
    assert state is not None
    assert [directory for _, _, directory in rig.policies.published] == [state.policy_dir]
    assert state.policy_dir != rig.policies.published_nuclei[0][2]


def test_up_sobe_a_cerca_do_nuclei_com_as_pastas_proprias_no_ambiente(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.manager.up(StackUpRequest(product="demo"))

    state = rig.states.state
    assert state is not None
    assert "scope-proxy-nuclei" in BASE_SERVICES
    assert "scope-proxy-nuclei" in state.projects[0].services
    env = rig.compose.envs["hdast"]
    assert state.nuclei_policy_dir is not None
    assert state.nuclei_audit_dir is not None
    assert env["HDAST_NUCLEI_POLICY_DIR"] == state.nuclei_policy_dir.as_posix()
    assert env["HDAST_NUCLEI_AUDIT_DIR"] == state.nuclei_audit_dir.as_posix()
    assert env["HDAST_SCOPE_POLICY_DIR"] == state.policy_dir.as_posix()


def test_stop_aciona_o_kill_das_duas_cercas(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))

    report = rig.manager.stop(FakeStopper(reachable=False), None)

    state = rig.states.state
    assert state is not None
    assert state.nuclei_policy_dir is not None
    assert (state.policy_dir / "KILL").exists()
    assert (state.nuclei_policy_dir / "KILL").exists()
    assert report.nuclei_kill_created is True
    assert report.nuclei_kill_file == str(state.nuclei_policy_dir / "KILL")


def test_stop_repetido_diz_que_o_kill_do_nuclei_ja_existia(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))

    rig.manager.stop(FakeStopper(), None)
    second = rig.manager.stop(FakeStopper(), None)

    assert (second.kill_created, second.nuclei_kill_created) == (False, False)


def test_stop_com_estado_antigo_sem_pasta_do_nuclei_aciona_so_o_kill_original(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    state = rig.states.state
    assert state is not None
    rig.states.state = state.model_copy(
        update={"nuclei_policy_dir": None, "nuclei_audit_dir": None}
    )

    report = rig.manager.stop(FakeStopper(), None)

    assert report.kill_created is True
    assert report.nuclei_kill_file is None
    assert report.nuclei_kill_created is False
