"""Confere o preparo de imagens com um executor de Compose em memória."""

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness_dast import __version__
from harness_dast.adapters.docker.compose import CommandResult
from harness_dast.domain.errors import ConfigError, ExternalToolError
from tests.integration import lab_images
from tests.integration.lab_images import (
    PILOT_IMAGE,
    PREBUILD_TIMEOUT,
    PREBUILT_TAG,
    build_session_images,
    prepare_session_images,
)


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


class InspectingCompose(FakeCompose):
    """Responde à conferência de imagens com `inspect_code` e conta os builds."""

    def __init__(self, inspect_code: int) -> None:
        super().__init__()
        self.inspect_code = inspect_code
        self.inspected: list[str] = []

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        if args[1:3] == ["image", "inspect"]:
            self.inspected = args[3:]
            return CommandResult(self.inspect_code, "", "")
        return super().__call__(args, env, cwd, timeout)


def test_reuses_images_quando_tag_pre_construida_existe(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = InspectingCompose(inspect_code=0)
    docker_env[PREBUILT_TAG] = "gh-abc123"

    images = prepare_session_images(tmp_path, docker_env, "outra", runner=compose)

    assert images == {
        "HDAST_ZAP_IMAGE": "hdast/zap:gh-abc123",
        "HDAST_SCOPE_PROXY_IMAGE": "hdast/scope-proxy:gh-abc123",
    }
    assert compose.commands == []
    assert compose.inspected == [*images.values(), PILOT_IMAGE]


def test_builds_with_the_tag_quando_imagem_da_tag_nao_existe(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = InspectingCompose(inspect_code=1)
    docker_env[PREBUILT_TAG] = "gh-abc123"

    images = prepare_session_images(tmp_path, docker_env, "outra", runner=compose)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:gh-abc123"
    assert len(compose.commands) == 2


def test_builds_with_default_tag_quando_variavel_ausente(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = InspectingCompose(inspect_code=0)

    images = prepare_session_images(tmp_path, docker_env, "sessao", runner=compose)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:sessao"
    assert compose.inspected == []
    assert len(compose.commands) == 2


@pytest.mark.parametrize("tag", ["com espaço", "-inicio", "a/b", "x" * 129])
def test_rejects_tag_quando_formato_invalido(
    tmp_path: Path, docker_env: dict[str, str], tag: str
) -> None:
    compose = InspectingCompose(inspect_code=0)
    docker_env[PREBUILT_TAG] = tag

    with pytest.raises(ConfigError, match=PREBUILT_TAG):
        prepare_session_images(tmp_path, docker_env, "sessao", runner=compose)

    assert compose.commands == []


def test_builds_with_default_tag_quando_variavel_esta_vazia(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = InspectingCompose(inspect_code=0)
    docker_env[PREBUILT_TAG] = ""

    images = prepare_session_images(tmp_path, docker_env, "sessao", runner=compose)

    assert images["HDAST_ZAP_IMAGE"] == "hdast/zap:sessao"


def test_builds_quando_conferencia_de_imagem_expira(
    tmp_path: Path, docker_env: dict[str, str]
) -> None:
    compose = InspectingCompose(inspect_code=0)

    def expires(
        args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        if args[1:3] == ["image", "inspect"]:
            raise subprocess.TimeoutExpired(args, timeout)
        return compose(args, env, cwd, timeout)

    docker_env[PREBUILT_TAG] = "gh-abc123"

    prepare_session_images(tmp_path, docker_env, "sessao", runner=expires)

    assert len(compose.commands) == 2


def test_prints_references_quando_main_prepara_a_tag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    refs = {"HDAST_ZAP_IMAGE": "hdast/zap:t", "HDAST_SCOPE_PROXY_IMAGE": "hdast/scope-proxy:t"}
    monkeypatch.setattr(lab_images, "prepare_session_images", lambda *_a, **_k: refs)

    assert lab_images.main(["t"]) == 0

    assert capsys.readouterr().out.splitlines() == [*refs.values(), PILOT_IMAGE]


def test_rejects_usage_quando_main_nao_recebe_a_tag(capsys: pytest.CaptureFixture[str]) -> None:
    assert lab_images.main([]) == 2
    assert "Uso:" in capsys.readouterr().err
