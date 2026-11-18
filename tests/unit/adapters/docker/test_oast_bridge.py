"""Inspeção da ponte com processo Docker falso, sem Docker real."""

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from harness_dast.adapters.docker.oast_bridge import DockerOastBridge, run_docker
from harness_dast.application.stack_models import ComposeProject, StackState
from harness_dast.domain.errors import ConfigError


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


def test_topology_and_callback_available_with_valid_data() -> None:
    bridge = _bridge(lambda: _state(), "a" * 12)
    assert bridge.inspect() is True
    assert bridge.callback() is True


def test_non_lab_product_has_no_bridge() -> None:
    bridge = _bridge(lambda: _state(None), "a" * 12)
    assert bridge.inspect() is False


@pytest.mark.parametrize("output", ["-argumento", "abc", "z" * 12, "a" * 12 + "\n" + "b" * 12])
def test_malformed_docker_output_is_unknown(output: str) -> None:
    bridge = _bridge(lambda: _state(), output)
    assert bridge.inspect() is None


def test_missing_container_means_unavailable() -> None:
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
def test_missing_network_connection_makes_bridge_unavailable(
    missing: tuple[str, str, str],
) -> None:
    docker = FakeDocker()
    docker.members.remove(missing)
    bridge = DockerOastBridge(lambda: _state(), {}, runner=docker.run)
    assert bridge.inspect() is False


def test_unreadable_state_makes_inspection_and_callback_unknown() -> None:
    def load() -> StackState | None:
        raise ConfigError("estado indisponivel")

    bridge = DockerOastBridge(load, {}, runner=FakeDocker().run)
    assert bridge.inspect() is None
    assert bridge.callback() is None


def test_callback_unavailable_without_managed_stack() -> None:
    bridge = _bridge(lambda: None, "a" * 12)
    assert bridge.inspect() is False
    assert bridge.callback() is False


def test_callback_unavailable_without_gateway() -> None:
    bridge = _bridge(lambda: _state(), "")
    assert bridge.callback() is False


@pytest.mark.parametrize("result", [None, (1, "erro")])
def test_docker_inspection_failure_produces_unknown_state(
    result: tuple[int, str] | None,
) -> None:
    def run(args: list[str], environ: Mapping[str, str]) -> tuple[int, str] | None:
        return result

    bridge = DockerOastBridge(lambda: _state(), {}, runner=run)
    assert bridge.inspect() is None
    assert bridge.callback() is None


@pytest.mark.parametrize(("result", "expected"), [(None, None), ((1, ""), False)])
def test_callback_execution_failure_is_not_success(
    result: tuple[int, str] | None,
    expected: bool | None,
) -> None:
    docker = FakeDocker()

    def run(args: list[str], environ: Mapping[str, str]) -> tuple[int, str] | None:
        return result if args[0] == "exec" else docker.run(args, environ)

    bridge = DockerOastBridge(lambda: _state(), {}, runner=run)
    assert bridge.callback() is expected


def test_missing_docker_command_produces_unknown_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda *args, **kwargs: None)
    assert run_docker(["ps"], {}) is None


@pytest.mark.parametrize(
    "failure", [OSError("indisponivel"), subprocess.TimeoutExpired("docker", 10)]
)
def test_docker_process_failure_produces_unknown_state(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr("shutil.which", lambda *args, **kwargs: "docker")

    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("subprocess.run", fail)
    assert run_docker(["ps"], {}) is None
