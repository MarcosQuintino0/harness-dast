from datetime import timedelta
from pathlib import Path

import pytest

from harness_dast import __version__
from harness_dast.application.scan_ports import RunningScans
from harness_dast.application.stack import StackManager, StackUpRequest
from harness_dast.application.stack_freshness import StackFreshnessCheck
from harness_dast.application.stack_models import LabAccountPaths
from harness_dast.domain.api_model import ApiSpec, Operation
from harness_dast.domain.errors import (
    ConfigError,
    ExternalToolError,
    ScopeViolation,
    StackBuildForbidden,
)
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.proxy_deadline import stack_validity_minutes
from harness_dast.domain.scan_result import ScanProgress
from harness_dast.domain.stack_binding import StackDigests
from tests.fakes.host import FakeHost, published_images
from tests.fakes.probe_ports import InMemorySpecs
from tests.fakes.profile_data import valid_profile, valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.runtime import FixedEntropy, ManualClock
from tests.fakes.stack import (
    CountingRandom,
    FakeBindingSource,
    FakeCompose,
    FakeStopper,
    InMemoryStackState,
    RecordingPolicyStore,
)


def lab_profile(product: str, host: str, port: int) -> ProductProfile:
    data = valid_profile_data(product)
    data["environment"]["base_url"] = f"http://{host}:{port}"
    data["scope"]["allow"] = [
        {
            "host": host,
            "scheme": "http",
            "port": port,
            "allow_local": True,
            "paths": ["/api/**"],
            "methods": ["GET", "POST"],
        }
    ]
    data["scope"]["deny_paths"] = []
    return ProductProfile.from_data(data)


class Rig:
    def __init__(
        self,
        tmp_path: Path,
        environ: dict[str, str] | None = None,
        running_scans: RunningScans | None = None,
        bindings: FakeBindingSource | None = None,
    ) -> None:
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(valid_profile("demo"))
        self.profiles.add(lab_profile("vampi", "vampi", 5000))
        self.profiles.add(lab_profile("clinica-piloto", "clinica-piloto", 8080))
        self.profiles.add(lab_profile("crapi", "crapi", 80))
        self.profiles.add(lab_profile("alvo-actuator", "alvo-actuator", 8080))
        self.host = FakeHost()
        self.compose = FakeCompose(self.host)
        self.states = InMemoryStackState(tmp_path)
        self.policies = RecordingPolicyStore()
        self.environ = environ or {}
        self.accounts = FakeCrapiAccounts()
        self.manager = StackManager(
            profiles=self.profiles,
            clock=ManualClock(),
            entropy=FixedEntropy(),
            random=CountingRandom(),
            policies=self.policies,
            compose=self.compose,
            images=self.host.stack_images(),
            states=self.states,
            environ=self.environ,
            repo_root=tmp_path / "repo",
            running_scans=running_scans,
            freshness=None if bindings is None else StackFreshnessCheck(self.states, bindings),
            crapi_accounts=self.accounts,
            specs=InMemorySpecs(
                ApiSpec(
                    title="lab",
                    version="1",
                    operations=tuple(
                        Operation(operation_id=name, method="post", path=f"/sample/{index}")
                        for index, name in enumerate(
                            ("signup", "login", "vehicle_resend_email", "add_vehicle")
                        )
                    ),
                )
            ),
        )


class FakeCrapiAccounts:
    def __init__(self) -> None:
        self.credentials: dict[str, str] = {}

    def provision(self, credentials: dict[str, str], paths: LabAccountPaths) -> None:
        self.credentials = dict(credentials)
        self.paths = paths


def test_crapi_sobe_projeto_proprio_e_cadastra_contas_sem_expor_valores(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": "-codex"})

    report = rig.manager.up(StackUpRequest(product="crapi"))

    state = rig.states.state
    assert state is not None
    assert [p.name for p in state.projects] == ["hdast-codex", "hdast-crapi-codex"]
    assert state.projects[1].remove_volumes is True
    assert state.projects[0].files == ("compose.yaml",)
    assert state.projects[1].files == ("compose.yaml",)
    assert "oast-gateway" not in state.projects[0].services
    assert rig.accounts.credentials == state.target_env
    assert rig.accounts.paths.signup == "/sample/0"
    assert rig.accounts.credentials["CRAPI_USER_A_PASSWORD"].startswith("Aa1#")
    assert all(value not in report.model_dump_json() for value in state.target_env.values())
    rig.manager.down()
    assert rig.compose.calls[-2:] == [("down", "hdast-crapi-codex"), ("down", "hdast-codex")]


def test_alvo_actuator_sobe_projeto_proprio_so_na_rede_do_lab_e_sorteia_a_chave(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": "-codex"})

    report = rig.manager.up(StackUpRequest(product="alvo-actuator"))

    state = rig.states.state
    assert state is not None
    assert state.lab_target == "alvo-actuator"
    assert [p.name for p in state.projects] == ["hdast-codex", "hdast-actuator-codex"]
    assert Path(state.projects[1].workdir).parts[-2:] == ("lab", "actuator")
    assert state.projects[1].files == ("compose.yaml",)
    assert state.projects[1].remove_volumes is False
    assert set(state.target_env) == {"ACTUATOR_API_KEY"}
    assert report.target_urls == {}
    rig.manager.down()
    assert rig.compose.calls[-2:] == [("down", "hdast-actuator-codex"), ("down", "hdast-codex")]


def test_crapi_oast_starts_isolated_bridge_and_stops_in_order(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": "-codex"})
    profile = lab_profile("crapi", "crapi", 80)
    rig.profiles.add(
        profile.model_copy(update={"scan": profile.scan.model_copy(update={"oast": True})})
    )

    rig.manager.up(StackUpRequest(product="crapi"))

    state = rig.states.state
    assert state is not None
    assert state.projects[0].files == ("compose.yaml", "lab/oast/compose.yaml")
    assert "oast-gateway" in state.projects[0].services
    assert state.projects[1].files == ("compose.yaml", "compose.oast.yaml")
    assert all(
        env["HDAST_OAST_NETWORK"] == "hdast-codex_oast_net" for env in rig.compose.envs.values()
    )
    rig.manager.down()
    assert rig.compose.calls[-2:] == [("down", "hdast-crapi-codex"), ("down", "hdast-codex")]


def test_regular_product_with_oast_does_not_receive_lab_bridge(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    profile = valid_profile("demo")
    rig.profiles.add(
        profile.model_copy(update={"scan": profile.scan.model_copy(update={"oast": True})})
    )

    rig.manager.up(StackUpRequest(product="demo"))

    state = rig.states.state
    assert state is not None
    assert state.projects[0].files == ("compose.yaml",)
    assert "oast-gateway" not in state.projects[0].services


def test_crapi_seguro_recusa_antes_de_derrubar_pilha_anterior(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    calls = list(rig.compose.calls)

    with pytest.raises(ConfigError, match="modo seguro"):
        rig.manager.up(StackUpRequest(product="crapi", vulnerable=False))

    assert rig.compose.calls == calls
    assert rig.states.state is not None
    assert rig.states.state.product == "demo"


def test_openapi_incompleto_preserva_pilha_anterior(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    state = rig.states.state
    calls = list(rig.compose.calls)
    policies = list(rig.policies.published)
    rig.manager._specs = InMemorySpecs(ApiSpec(title="incompleto", version="1"))

    with pytest.raises(ConfigError, match="não existe"):
        rig.manager.up(StackUpRequest(product="crapi"))

    assert rig.states.state == state
    assert rig.compose.calls == calls
    assert rig.policies.published == policies


def test_falha_no_cadastro_mantem_estado_para_derrubar_projetos(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    class BrokenAccounts:
        def provision(self, credentials: dict[str, str], paths: LabAccountPaths) -> None:
            raise ExternalToolError("cadastro falhou", hint="Derrube a pilha.")

    rig.manager._crapi_accounts = BrokenAccounts()
    with pytest.raises(ExternalToolError):
        rig.manager.up(StackUpRequest(product="crapi"))

    assert rig.states.state is not None
    rig.manager.down()
    assert rig.compose.calls[-2:] == [("down", "hdast-crapi"), ("down", "hdast")]


def test_up_gera_chave_politica_e_estado_e_sobe_so_o_compose_raiz_para_produto_externo(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)

    report = rig.manager.up(StackUpRequest(product="demo"))

    state = rig.states.state
    assert state is not None
    assert len(state.zap_api_key) == 48
    assert report.running is True
    assert report.lab_target is None
    assert [project.name for project in state.projects] == ["hdast"]
    assert rig.policies.published[0][0] == state.run_id
    env = rig.compose.envs["hdast"]
    assert env["HDAST_ZAP_API_KEY"] == state.zap_api_key
    assert env["HDAST_SCOPE_POLICY_DIR"] == state.policy_dir.as_posix()


def test_up_uses_existing_images_without_building(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.manager.up(StackUpRequest(product="demo"))

    assert rig.compose.builds["hdast"] is False
    assert rig.compose.envs["hdast"]["HDAST_SCOPE_PROXY_IMAGE"] == rig.host.images["scope-proxy"]
    assert ("build", "hdast") not in rig.compose.calls


def test_up_passes_digest_references_to_compose_when_lock_is_present(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    lock = published_images()
    rig.host.images_lock = lock
    zap = lock.images.zap.reference()
    proxy = lock.images.scope_proxy.reference()
    rig.host.present = {zap, proxy}
    rig.host.versions[proxy] = __version__

    rig.manager.up(StackUpRequest(product="demo"))

    assert rig.compose.envs["hdast"]["HDAST_ZAP_IMAGE"] == zap
    assert rig.compose.envs["hdast"]["HDAST_SCOPE_PROXY_IMAGE"] == proxy
    assert rig.compose.builds["hdast"] is False


@pytest.mark.parametrize("service", ["zap", "scope-proxy"])
def test_up_preserves_previous_stack_when_an_image_is_missing(tmp_path: Path, service: str) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    previous = rig.states.state
    rig.host.present.remove(rig.host.images[service])

    with pytest.raises(ExternalToolError, match="ausentes") as error:
        rig.manager.up(StackUpRequest(product="vampi"))

    assert "hdast stack pull" in (error.value.hint or "")
    assert rig.states.state == previous
    assert rig.compose.calls == [("up", "hdast")]


@pytest.mark.parametrize("version", ["0.0.0", None])
def test_up_refuses_an_incompatible_proxy_before_creating_state(
    tmp_path: Path, version: str | None
) -> None:
    rig = Rig(tmp_path)
    rig.host.versions[rig.host.images["scope-proxy"]] = version

    with pytest.raises(ExternalToolError, match="A CLI exige a versão") as error:
        rig.manager.up(StackUpRequest(product="demo"))

    assert __version__ in error.value.message
    assert "hdast stack pull" in (error.value.hint or "")
    assert rig.states.state is None
    assert rig.compose.calls == []


@pytest.mark.parametrize("flag", [False, True])
def test_up_builds_local_images_when_requested(tmp_path: Path, flag: bool) -> None:
    rig = Rig(tmp_path, {} if flag else {"HDAST_STACK_BUILD": "1"})
    rig.host.present.clear()

    rig.manager.up(StackUpRequest(product="demo", build=flag))

    local_proxy = "hdast/scope-proxy:local"
    assert rig.host.versions[local_proxy] == __version__
    assert rig.compose.envs["hdast"]["HDAST_SCOPE_PROXY_IMAGE"] == local_proxy
    assert rig.compose.calls == [("build", "hdast"), ("up", "hdast")]


@pytest.mark.parametrize("flag", [False, True], ids=["env", "flag"])
@pytest.mark.parametrize("packaged", [False, True], ids=["missing-contexts", "lock-present"])
def test_up_rejects_local_build_before_docker_when_outside_clone(
    tmp_path: Path, flag: bool, packaged: bool
) -> None:
    rig = Rig(tmp_path, {} if flag else {"HDAST_STACK_BUILD": "1"})
    # A presença do arquivo de digests basta para recusar mesmo se os contextos existirem.
    rig.host.build_contexts = packaged
    rig.host.images_lock = published_images() if packaged else None

    with pytest.raises(StackBuildForbidden, match=__version__) as error:
        rig.manager.up(StackUpRequest(product="demo", build=flag))

    assert error.value.hint
    assert rig.host.docker_calls == 0
    assert rig.compose.calls == []
    assert rig.states.state is None


def test_up_checks_the_proxy_version_after_local_build(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_BUILD": "1"})
    rig.compose.built_proxy_version = "0.0.0"

    with pytest.raises(ExternalToolError, match="A CLI exige a versão"):
        rig.manager.up(StackUpRequest(product="demo"))

    assert rig.states.state is None
    assert not rig.compose.running


@pytest.mark.parametrize(
    ("value", "explicit_build", "expected"),
    [
        (None, False, None),
        ("0", False, None),
        ("true", False, None),
        ("reuse", False, False),
        ("reuse", True, True),
        ("1", False, True),
    ],
)
def test_selects_pilot_build_quando_configurado(
    tmp_path: Path, value: str | None, explicit_build: bool, expected: bool | None
) -> None:
    env = {} if value is None else {"HDAST_STACK_BUILD": value}
    rig = Rig(tmp_path, env)

    rig.manager.up(StackUpRequest(product="clinica-piloto", build=explicit_build))

    assert rig.compose.builds["hdast-pilotrun"] is expected


def test_reuse_disables_builds_when_outside_clone(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_BUILD": "reuse"})
    rig.host.build_contexts = False
    lock = published_images()
    rig.host.images_lock = lock
    proxy = lock.images.scope_proxy.reference()
    rig.host.present = {lock.images.zap.reference(), proxy}
    rig.host.versions[proxy] = __version__

    rig.manager.up(StackUpRequest(product="clinica-piloto"))

    assert rig.compose.builds == {"hdast": False, "hdast-pilotrun": False}
    assert rig.compose.calls == [("up", "hdast"), ("up", "hdast-pilotrun")]


def test_sufixo_isola_projetos_e_rede_tambem_no_down(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": "-codex"})

    rig.manager.up(StackUpRequest(product="clinica-piloto"))
    state = rig.states.state
    assert state is not None
    assert [project.name for project in state.projects] == ["hdast-codex", "hdast-pilotrun-codex"]
    assert rig.compose.envs["hdast-pilotrun-codex"]["HDAST_LAB_NETWORK"] == "hdast-codex_lab_net"
    rig.environ["HDAST_STACK_PROJECT_SUFFIX"] = "-outro"
    rig.manager.down()
    assert ("down", "hdast-codex") in rig.compose.calls


@pytest.mark.parametrize("suffix", ["codex", "-UPPER", "-a_b", "-", "-" + "a" * 21])
def test_sufixo_invalido_recusa_antes_de_tocar_pilha(tmp_path: Path, suffix: str) -> None:
    rig = Rig(tmp_path, {"HDAST_STACK_PROJECT_SUFFIX": suffix})

    with pytest.raises(ConfigError, match="Sufixo"):
        rig.manager.up(StackUpRequest(product="demo"))

    assert rig.compose.calls == []
    assert rig.policies.published == []


def test_up_respeita_a_chave_ja_definida_no_ambiente(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"HDAST_ZAP_API_KEY": "minha-chave-fixa"})

    rig.manager.up(StackUpRequest(product="demo"))

    assert rig.compose.envs["hdast"]["HDAST_ZAP_API_KEY"] == "minha-chave-fixa"


def test_up_do_vampi_sobe_o_alvo_no_compose_raiz_com_o_perfil_lab(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.manager.up(StackUpRequest(product="vampi", vulnerable=False, token_ttl_seconds=30))

    project = rig.compose.running["hdast"]
    assert project.profiles == ("lab",)
    assert "vampi" in project.services
    assert rig.compose.envs["hdast"]["HDAST_VAMPI_VULNERABLE"] == "0"
    assert rig.compose.envs["hdast"]["HDAST_VAMPI_TOKEN_TTL"] == "30"  # noqa: S105


def test_up_do_piloto_anexa_o_alvo_em_projeto_proprio_com_credenciais_descartaveis(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, {"PILOT_ADMIN_USERNAME": "definido-pela-pessoa"})

    report = rig.manager.up(StackUpRequest(product="clinica-piloto", vulnerable=True))

    state = rig.states.state
    assert state is not None
    assert [project.name for project in state.projects] == ["hdast", "hdast-pilotrun"]
    assert "PILOT_ADMIN_USERNAME" not in state.target_env
    assert set(state.target_env) == {
        "PILOT_ADMIN_PASSWORD",
        "PILOT_MEDICO_USERNAME",
        "PILOT_MEDICO_PASSWORD",
        "PILOT_MEDICO_B_USERNAME",
        "PILOT_MEDICO_B_PASSWORD",
        "PILOT_PACIENTE_A_USERNAME",
        "PILOT_PACIENTE_A_PASSWORD",
        "PILOT_PACIENTE_B_USERNAME",
        "PILOT_PACIENTE_B_PASSWORD",
    }
    assert len(set(state.target_env.values())) == 9
    assert rig.environ["PILOT_ADMIN_USERNAME"] == "definido-pela-pessoa"
    assert rig.compose.envs["hdast-pilotrun"]["PILOT_VULNERABLE"] == "1"
    assert report.target_urls["management"].startswith("http://127.0.0.1:")
    assert state.zap_api_key not in report.model_dump_json()


def test_up_preserva_credencial_do_segundo_medico_fornecida_pela_pessoa(tmp_path: Path) -> None:
    rig = Rig(tmp_path, {"PILOT_MEDICO_B_USERNAME": "conta-fornecida"})

    rig.manager.up(StackUpRequest(product="clinica-piloto"))

    assert rig.states.state is not None
    assert "PILOT_MEDICO_B_USERNAME" not in rig.states.state.target_env
    assert rig.environ["PILOT_MEDICO_B_USERNAME"] == "conta-fornecida"
    assert "PILOT_MEDICO_B_PASSWORD" in rig.states.state.target_env


def test_up_com_janela_fechada_levanta_escopo_e_nao_toca_o_docker(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    data = valid_profile_data("fechado")
    data["scope"]["authorization"]["valid_until"] = "2000-01-01"
    rig.profiles.add(ProductProfile.from_data(data))

    with pytest.raises(ScopeViolation):
        rig.manager.up(StackUpRequest(product="fechado"))

    assert rig.compose.calls == []
    assert rig.states.state is None
    assert rig.policies.published == []


def test_estado_e_gravado_antes_de_subir_para_o_down_limpar_uma_subida_que_falhou(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)
    rig.compose.fail_on = "up"

    with pytest.raises(ExternalToolError):
        rig.manager.up(StackUpRequest(product="demo"))

    assert rig.states.state is not None
    rig.compose.fail_on = None
    rig.manager.down()
    assert rig.states.state is None


def test_segundo_up_derruba_a_pilha_anterior_e_avisa(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="clinica-piloto"))

    report = rig.manager.up(StackUpRequest(product="demo"))

    assert ("down", "hdast-pilotrun") in rig.compose.calls
    assert "hdast-pilotrun" not in rig.compose.running
    assert "derrubada" in report.warnings[0]


def test_down_derruba_o_alvo_antes_da_pilha_base_e_esquece_o_estado(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="clinica-piloto"))
    rig.compose.calls.clear()

    rig.manager.down()

    assert rig.compose.calls == [("down", "hdast-pilotrun"), ("down", "hdast")]
    assert rig.states.state is None


def test_down_que_falha_mantem_o_estado_para_nova_tentativa(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    rig.compose.fail_on = "down"

    with pytest.raises(ExternalToolError):
        rig.manager.down()

    assert rig.states.state is not None


def test_status_sem_pilha_diz_que_nao_ha_e_com_pilha_mostra_a_trava(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    assert rig.manager.status().managed is False

    rig.manager.up(StackUpRequest(product="demo"))
    rig.manager.stop(FakeStopper(), None)

    status = rig.manager.status()
    assert status.managed is True
    assert status.kill_switch is True


def test_status_diz_que_a_pilha_esta_desatualizada_e_como_recriar(tmp_path: Path) -> None:
    recorded = StackDigests(profile_sha256="a" * 64, approval_sha256="b" * 64)
    changed = StackDigests(profile_sha256="c" * 64, approval_sha256="b" * 64)
    rig = Rig(tmp_path, bindings=FakeBindingSource(recorded, changed))
    rig.manager.up(StackUpRequest(product="demo"))

    status = rig.manager.status()

    assert status.binding == "stale"
    assert status.stale_parts == ("profile",)
    assert status.stale_message is not None
    assert "hdast stack down" in status.stale_message


def test_status_diz_fresh_quando_corresponde_e_nada_sem_a_conferencia(tmp_path: Path) -> None:
    same = StackDigests(profile_sha256="a" * 64, approval_sha256="b" * 64)
    fresh = Rig(tmp_path / "a", bindings=FakeBindingSource(same, same))
    fresh.manager.up(StackUpRequest(product="demo"))
    plain = Rig(tmp_path / "b")
    plain.manager.up(StackUpRequest(product="demo"))

    assert fresh.manager.status().binding == "fresh"
    assert fresh.manager.status().stale_message is None
    assert plain.manager.status().binding is None


def test_stop_aciona_o_kill_mesmo_com_o_zap_fora_do_ar(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))

    report = rig.manager.stop(FakeStopper(reachable=False), None)

    state = rig.states.state
    assert state is not None
    assert (state.policy_dir / "KILL").exists()
    assert report.kill_created is True
    assert report.zap_reachable is False
    assert report.zap_message


def test_stop_para_as_varreduras_e_repetir_nao_falha(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="demo"))
    stopper = FakeStopper(running=3)

    first = rig.manager.stop(stopper, None)
    second = rig.manager.stop(stopper, None)

    assert first.zap_scans_stopped == 3
    assert (first.kill_created, second.kill_created) == (True, False)


class _Scans:
    def __init__(self, *items: ScanProgress) -> None:
        self._items = items

    def running(self) -> tuple[ScanProgress, ...]:
        return self._items


def _progress(updated_at: str, run_id: str = "r1") -> ScanProgress:
    return ScanProgress(
        run_id=run_id,
        phase="scanning",
        status="running",
        index=3,
        total=10,
        operation_id="buscar",
        progress=40,
        updated_at=updated_at,
    )


def test_stop_informa_a_varredura_em_andamento_e_ignora_andamento_velho(tmp_path: Path) -> None:
    now = ManualClock().now()
    fresh = _progress((now - timedelta(seconds=5)).isoformat(), "novo")
    stale = _progress((now - timedelta(hours=2)).isoformat(), "velho")
    rig = Rig(tmp_path, running_scans=_Scans(fresh, stale))
    rig.manager.up(StackUpRequest(product="demo"))

    report = rig.manager.stop(FakeStopper(running=1), None)

    assert [item.run_id for item in report.scans_running] == ["novo"]
    assert report.scans_running[0].operation_id == "buscar"


def test_up_com_oracle_sobe_o_perfil_oracle_e_gera_as_credenciais_do_banco(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.manager.up(StackUpRequest(product="clinica-piloto", oracle=True))

    state = rig.states.state
    assert state is not None
    attached = state.projects[1]
    assert attached.profiles == ("oracle",)
    assert "compose.oracle-port.yaml" in attached.files
    env = state.target_env
    assert env["PILOT_DB_PASSWORD"] == env["PILOT_ORACLE_PASSWORD"]
    assert env["PILOT_ORACLE_CLEANUP_CONNECTION"].startswith("127.0.0.1:")
    assert env["PILOT_ORACLE_CLEANUP_USER"] == "HDAST_LIMPEZA"
    assert env["PILOT_ORACLE_CLEANUP_PASSWORD"] != env["PILOT_ORACLE_PASSWORD"]


def test_up_com_oracle_em_outro_alvo_falha_com_orientacao(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    with pytest.raises(ConfigError, match="Clínica Piloto"):
        rig.manager.up(StackUpRequest(product="vampi", oracle=True))


@pytest.mark.parametrize(
    ("up_request", "message"),
    [
        (StackUpRequest(product="crapi", oracle=True), "Clínica Piloto"),
        (StackUpRequest(product="vampi", oracle=True), "Clínica Piloto"),
        (StackUpRequest(product="crapi", vulnerable=False), "modo seguro"),
        (StackUpRequest(product="crapi", token_ttl_seconds=30), "ajuste de token"),
    ],
)
def test_opcao_invalida_preserva_pilha_crapi_anterior(
    tmp_path: Path, up_request: StackUpRequest, message: str
) -> None:
    rig = Rig(tmp_path)
    rig.manager.up(StackUpRequest(product="crapi"))
    original_state = rig.states.state
    assert original_state is not None
    policy_file = original_state.policy_dir / "policy.json"
    policy_content = policy_file.read_bytes()
    published = list(rig.policies.published)
    calls = list(rig.compose.calls)
    projects = dict(rig.compose.running)

    with pytest.raises(ConfigError, match=message):
        rig.manager.up(up_request)

    assert rig.states.state == original_state
    assert policy_file.read_bytes() == policy_content
    assert rig.policies.published == published
    assert rig.compose.calls == calls
    assert rig.compose.running == projects


def test_stop_sem_pilha_usa_a_pasta_informada_ou_falha_com_orientacao(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    folder = tmp_path / "politica"
    folder.mkdir()

    report = rig.manager.stop(FakeStopper(), folder)

    assert report.stack_managed is False
    assert (folder / "KILL").exists()
    with pytest.raises(ConfigError, match="política"):
        rig.manager.stop(FakeStopper(), None)


def test_up_da_validade_a_pilha_com_folga_sobre_a_duracao_da_execucao(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    profile = rig.profiles.load("demo")

    rig.manager.up(StackUpRequest(product="demo"))

    _, not_after, _ = rig.policies.published[0]
    started = ManualClock().now()
    assert not_after > started + timedelta(minutes=profile.limits.max_duration_minutes)
    assert not_after <= started + timedelta(minutes=stack_validity_minutes(profile))
