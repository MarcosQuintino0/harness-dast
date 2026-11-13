from pathlib import Path

import pytest

from harness_dast.application.stack import StackManager, StackUpRequest
from harness_dast.domain.errors import ConfigError, ExternalToolError, ScopeViolation
from harness_dast.domain.profile import ProductProfile
from tests.fakes.profile_data import valid_profile, valid_profile_data
from tests.fakes.profile_repository import InMemoryProfileRepository
from tests.fakes.runtime import FixedEntropy, ManualClock
from tests.fakes.stack import (
    CountingRandom,
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
    def __init__(self, tmp_path: Path, environ: dict[str, str] | None = None) -> None:
        self.profiles = InMemoryProfileRepository()
        self.profiles.add(valid_profile("demo"))
        self.profiles.add(lab_profile("vampi", "vampi", 5000))
        self.profiles.add(lab_profile("clinica-piloto", "clinica-piloto", 8080))
        self.compose = FakeCompose()
        self.states = InMemoryStackState(tmp_path)
        self.policies = RecordingPolicyStore()
        self.environ = environ or {}
        self.manager = StackManager(
            profiles=self.profiles,
            clock=ManualClock(),
            entropy=FixedEntropy(),
            random=CountingRandom(),
            policies=self.policies,
            compose=self.compose,
            states=self.states,
            environ=self.environ,
            repo_root=tmp_path / "repo",
        )


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
    assert len(state.target_env) == 7
    assert len(set(state.target_env.values())) == 7
    assert rig.compose.envs["hdast-pilotrun"]["PILOT_VULNERABLE"] == "1"
    assert report.target_urls["management"].startswith("http://127.0.0.1:")
    assert state.zap_api_key not in report.model_dump_json()


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


def test_stop_sem_pilha_usa_a_pasta_informada_ou_falha_com_orientacao(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    folder = tmp_path / "politica"
    folder.mkdir()

    report = rig.manager.stop(FakeStopper(), folder)

    assert report.stack_managed is False
    assert (folder / "KILL").exists()
    with pytest.raises(ConfigError, match="política"):
        rig.manager.stop(FakeStopper(), None)
