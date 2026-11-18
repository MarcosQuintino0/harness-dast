"""Inspeção da ponte com processo Docker falso, sem Docker real."""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from harness_dast.adapters.docker.oast_bridge import DockerOastBridge
from harness_dast.application.stack_models import ComposeProject, StackState


class FakeDocker:
    """Representa contêineres em redes distintas e aceita consulta por filtros."""

    def __init__(self, output: str = "a" * 12) -> None:
        self.output = output
        self.members = {
            ("hdast-x", "oast-gateway", "hdast-x_oast_net"),
            ("hdast-x", "oast-gateway", "hdast-x_zap_net"),
            ("crapi-x", "crapi-workshop", "hdast-x_oast_net"),
        }

    def run(self, args: list[str], environ: Mapping[str, str]) -> tuple[int, str] | None:
        if args[0] == "exec":
            return (0, "")
        filters = [args[index + 1] for index, value in enumerate(args) if value == "--filter"]
        project = next(item.split("=", 2)[-1] for item in filters if "compose.project=" in item)
        service = next(item.split("=", 2)[-1] for item in filters if "compose.service=" in item)
        network = next(item.split("=", 1)[-1] for item in filters if item.startswith("network="))
        return (0, self.output if (project, service, network) in self.members else "")


def _bridge(load_state: Callable[[], StackState | None], output: str) -> DockerOastBridge:
    return DockerOastBridge(load_state, {}, runner=FakeDocker(output).run)


def _state(target: str | None = "crapi") -> StackState:
    main = ComposeProject(name="hdast-x", workdir=".", files=("compose.yaml",))
    lab = ComposeProject(name="crapi-x", workdir=".", files=("compose.yaml",))
    return StackState(
        product="test",
        run_id="test",
        started_at="test",
        not_after="test",
        lab_target=target,
        zap_api_key="synthetic",
        zap_url="http://zap",
        auth_proxy_url="http://proxy",
        policy_dir=Path("."),
        audit_dir=Path("."),
        projects=(main, lab),
    )


def test_topologia_e_callback_disponiveis_com_dados_validos() -> None:
    bridge = _bridge(lambda: _state(), "a" * 12)
    assert bridge.inspect() is True
    assert bridge.callback() is True


def test_produto_fora_do_laboratorio_nao_recebe_ponte() -> None:
    bridge = _bridge(lambda: _state(None), "a" * 12)
    assert bridge.inspect() is False


@pytest.mark.parametrize("output", ["-argumento", "abc", "z" * 12, "a" * 12 + "\n" + "b" * 12])
def test_saida_docker_malformada_e_desconhecida(output: str) -> None:
    bridge = _bridge(lambda: _state(), output)
    assert bridge.inspect() is None


def test_ausencia_do_conteiner_e_indisponibilidade() -> None:
    bridge = _bridge(lambda: _state(), "")
    assert bridge.inspect() is False


@pytest.mark.parametrize(
    "missing",
    [
        ("hdast-x", "oast-gateway", "hdast-x_oast_net"),
        ("hdast-x", "oast-gateway", "hdast-x_zap_net"),
        ("crapi-x", "crapi-workshop", "hdast-x_oast_net"),
    ],
)
def test_sem_cada_conexao_necessaria_a_ponte_fica_indisponivel(
    missing: tuple[str, str, str],
) -> None:
    docker = FakeDocker()
    docker.members.remove(missing)
    bridge = DockerOastBridge(lambda: _state(), {}, runner=docker.run)
    assert bridge.inspect() is False
