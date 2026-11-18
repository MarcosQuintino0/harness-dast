"""Confere o preparo de imagens com um executor de Compose em memória."""

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness_dast import __version__
from harness_dast.adapters.docker.compose import CommandResult
from harness_dast.domain.errors import ExternalToolError
from tests.integration.lab_images import PREBUILD_TIMEOUT, build_session_images


class FakeCompose:
    """Devolve o resultado do build e guarda as entradas recebidas pelo processo."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.commands: list[tuple[Path, list[str], float]] = []
        self.environ: dict[str, str] = {}

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.commands.append((cwd, args[1:], timeout))
        self.environ = dict(env)
        return CommandResult(self.code, "", "saída interna")


@pytest.fixture
def docker_env(tmp_path: Path) -> dict[str, str]:
    executable = tmp_path / ("docker.exe" if os.name == "nt" else "docker")
    executable.touch(mode=0o700)
    return {"PATH": str(tmp_path)}


def test_builds_each_project_quando_prepara_imagens(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose()
    repo = tmp_path / "checkout"

    build_session_images(repo, "sessao", docker_env, runner=compose)

    assert compose.commands == [
        (repo, ["compose", "-f", "compose.yaml", "build", "zap", "scope-proxy"], PREBUILD_TIMEOUT),
        (
            repo / "lab" / "pilot",
            ["compose", "-f", "compose.yaml", "-f", "compose.lab-net.yaml", "build", "pilot"],
            PREBUILD_TIMEOUT,
        ),
    ]


def test_uses_checkout_tags_quando_ambiente_tem_overrides(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose()
    docker_env.update(
        HDAST_SCOPE_PROXY_IMAGE="outra:imagem",
        HDAST_IMAGE_VERSION="outra",
        COMPOSE_ENV_FILES="outro-arquivo",
        PILOT_ADMIN_USERNAME="outra",
    )

    images = build_session_images(tmp_path, "sessao", docker_env, runner=compose)

    expected = {
        "HDAST_ZAP_IMAGE": "hdast/zap:sessao",
        "HDAST_SCOPE_PROXY_IMAGE": "hdast/scope-proxy:sessao",
    }
    assert images == expected
    assert {key: compose.environ[key] for key in expected} == images
    assert compose.environ["HDAST_IMAGE_VERSION"] == __version__
    assert compose.environ["PILOT_ADMIN_USERNAME"] == "lab-build"
    assert compose.environ["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert "COMPOSE_ENV_FILES" not in compose.environ


def test_reports_failure_quando_compose_recusa_build(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = FakeCompose(code=7)

    with pytest.raises(ExternalToolError, match="build de zap, scope-proxy falhou com código 7"):
        build_session_images(tmp_path, "sessao", docker_env, runner=compose)

    assert len(compose.commands) == 1


def test_reports_timeout_quando_build_ultrapassa_prazo(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    def expires(
        args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        raise subprocess.TimeoutExpired(args, timeout)

    with pytest.raises(ExternalToolError, match=f"ultrapassou {PREBUILD_TIMEOUT} s"):
        build_session_images(tmp_path, "sessao", docker_env, runner=expires)
