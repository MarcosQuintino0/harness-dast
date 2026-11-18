"""`SystemHost`: inspeção só de leitura, sem shell, com prazo e sem Docker de verdade."""

import socket
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness_dast.adapters.docker.compose import CommandResult, default_repo_root
from harness_dast.adapters.docker.host import (
    DOCKER_TIMEOUT_SECONDS,
    PULL_TIMEOUT_SECONDS,
    SystemHost,
)
from harness_dast.application.stack_images import ImageInfo
from harness_dast.domain.errors import ConfigError, ExternalToolError

BASE_ZAP = "zaproxy/zap-stable:2.17.0@sha256:" + "a" * 64
COMPOSE = f"""\
services:
  zap:
    image: {BASE_ZAP}
  scope-proxy:
    build: ./docker/scope-proxy
    image: ${{HDAST_SCOPE_PROXY_IMAGE:-hdast/scope-proxy:local}}
  vampi:
    image: erev0s/vampi:latest@sha256:{"b" * 64}
  sem-imagem:
    build: ./x
"""


class Recorder:
    def __init__(self, result: CommandResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[list[str], float]] = []

    def __call__(
        self, args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
    ) -> CommandResult:
        self.calls.append((args, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def fake_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name, **_k: name)


def host(runner: Recorder, root: Path | None = None) -> SystemHost:
    return SystemHost({"PATH": ""}, runner=runner, repo_root=root)


def test_docker_version_returns_the_server_version_with_a_timeout() -> None:
    runner = Recorder(CommandResult(0, "27.3.1\n", ""))

    assert host(runner).docker_version() == "27.3.1"

    args, timeout = runner.calls[0]
    assert args[:2] == ["docker", "version"]
    assert timeout == DOCKER_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(CommandResult(1, "", "Cannot connect to the Docker daemon"), id="down"),
        pytest.param(CommandResult(0, "  \n", ""), id="empty"),
    ],
)
def test_docker_version_raises_with_the_fix_when_docker_does_not_answer(
    result: CommandResult,
) -> None:
    with pytest.raises(ExternalToolError) as caught:
        host(Recorder(result)).docker_version()

    assert "Docker Desktop" in (caught.value.hint or "")


def test_docker_version_raises_when_the_command_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)

    with pytest.raises(ExternalToolError, match="não foi encontrado"):
        host(Recorder(CommandResult(0, "x", ""))).docker_version()


def test_docker_version_raises_when_it_times_out() -> None:
    runner = Recorder(subprocess.TimeoutExpired("docker", 20))

    with pytest.raises(ExternalToolError, match="não respondeu em 20 s"):
        host(runner).docker_version()


def test_docker_version_raises_when_the_process_cannot_start() -> None:
    with pytest.raises(ExternalToolError, match="Não foi possível executar"):
        host(Recorder(OSError("boom"))).docker_version()


def test_inspect_image_returns_the_oci_version_when_present() -> None:
    runner = Recorder(CommandResult(0, '"1.12.2"\n', ""))

    assert host(runner).inspect_image("zap:1@sha256:aaa") == ImageInfo(version="1.12.2")
    assert runner.calls[0][0][:3] == ["docker", "image", "inspect"]
    assert runner.calls[0][0][-1] == "zap:1@sha256:aaa"


@pytest.mark.parametrize("label", ['""', "null"])
def test_inspect_image_reports_a_missing_label(label: str) -> None:
    runner = Recorder(CommandResult(0, label, ""))

    assert host(runner).inspect_image("zap:1") == ImageInfo()


@pytest.mark.parametrize("label", ["quebrado", "30", '"rótulo com quebra\\n"'])
def test_inspect_image_refuses_malformed_metadata(label: str) -> None:
    runner = Recorder(CommandResult(0, label, ""))

    with pytest.raises(ExternalToolError, match="metadados inválidos"):
        host(runner).inspect_image("zap:1")


def test_inspect_image_returns_none_when_docker_says_no_such_image() -> None:
    runner = Recorder(CommandResult(1, "", "Error response from daemon: No such image: zap:1"))

    assert host(runner).inspect_image("zap:1") is None


def test_inspect_image_raises_when_the_daemon_is_down() -> None:
    runner = Recorder(CommandResult(1, "", "Cannot connect to the Docker daemon"))

    with pytest.raises(ExternalToolError, match="não conseguiu consultar"):
        host(runner).inspect_image("zap:1")


def test_pull_image_downloads_the_reference_with_a_timeout() -> None:
    runner = Recorder(CommandResult(0, "", ""))

    host(runner).pull_image("zap:1")

    assert runner.calls == [(["docker", "image", "pull", "zap:1"], PULL_TIMEOUT_SECONDS)]


def test_pull_image_explains_registry_failure_without_repeating_process_output() -> None:
    runner = Recorder(CommandResult(1, "", "texto bruto do Docker"))

    with pytest.raises(ExternalToolError, match="baixar a imagem zap:1") as caught:
        host(runner).pull_image("zap:1")

    assert "texto bruto" not in caught.value.message
    assert "registro" in (caught.value.hint or "")


# ----------------------------------------------------------------------- compose


def test_compose_images_lists_only_the_requested_services_that_have_an_image(
    tmp_path: Path,
) -> None:
    (tmp_path / "compose.yaml").write_text(COMPOSE, encoding="utf-8")

    images = host(Recorder(CommandResult(0, "", "")), tmp_path).compose_images(
        ("zap", "scope-proxy", "sem-imagem", "inexistente", "zap"), {}
    )

    assert images == {
        "zap": BASE_ZAP,
        "scope-proxy": "hdast/scope-proxy:local",
    }


@pytest.mark.parametrize("override", [None, "", "registry.example/proxy:teste@sha256:" + "a" * 64])
def test_compose_images_shares_the_versioned_proxy_reference_with_vampi_tls(
    override: str | None,
) -> None:
    env = {"HDAST_SCOPE_PROXY_IMAGE": override} if override is not None else {}
    images = SystemHost(env).compose_images(("zap", "scope-proxy", "vampi-tls"), {})
    package = tomllib.loads((default_repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    version = package["project"]["version"]
    expected = override or f"ghcr.io/marcosquintino0/hdast-scope-proxy:{version}"

    assert images == {
        "zap": f"ghcr.io/marcosquintino0/hdast-zap:{version}",
        "scope-proxy": expected,
        "vampi-tls": expected,
    }


@pytest.mark.parametrize(
    "ref",
    ["--help", "https://person:fake@host/image", "https://host/image?q=secret", "imagem ou outra"],
)
def test_compose_refuses_invalid_image_overrides_without_echoing_them(ref: str) -> None:
    system = SystemHost({"HDAST_SCOPE_PROXY_IMAGE": ref})

    with pytest.raises(ConfigError, match="do serviço scope-proxy é inválida") as caught:
        system.compose_images(("scope-proxy",), {})

    assert ref not in caught.value.message


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(None, id="missing"),
        pytest.param("services: [", id="malformed_yaml"),
        pytest.param("- a\n- b\n", id="not_a_mapping"),
        pytest.param("version: '3'\n", id="no_services"),
        pytest.param("services: texto\n", id="services_not_a_mapping"),
    ],
)
def test_compose_images_raises_config_error_when_compose_is_unusable(
    tmp_path: Path, content: str | None
) -> None:
    if content is not None:
        (tmp_path / "compose.yaml").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigError):
        host(Recorder(CommandResult(0, "", "")), tmp_path).compose_images(("zap",), {})


def test_compose_images_refuses_an_oversized_compose_file(tmp_path: Path) -> None:
    (tmp_path / "compose.yaml").write_text("services: {}\n" + "# x\n" * 100_000, encoding="utf-8")

    with pytest.raises(ConfigError, match="grande demais"):
        host(Recorder(CommandResult(0, "", "")), tmp_path).compose_images(("zap",), {})


# ------------------------------------------------------------------------- portas


def test_port_is_free_for_an_unused_port_and_busy_for_a_listening_one() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        busy = listener.getsockname()[1]
        free_check = host(Recorder(CommandResult(0, "", "")))

        assert free_check.port_is_free(busy) is False

    assert free_check.port_is_free(busy) is True


# --------------------------------------------------------------------------- uv


def test_uv_version_parses_the_second_word() -> None:
    runner = Recorder(CommandResult(0, "uv 0.5.1 (abc 2025-01-01)\n", ""))

    assert host(runner).uv_version() == "0.5.1"


def test_uv_version_is_none_when_uv_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda *_a, **_k: None)

    assert host(Recorder(CommandResult(0, "uv 1", ""))).uv_version() is None


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(CommandResult(1, "", "erro"), id="nonzero"),
        pytest.param(CommandResult(0, "", ""), id="empty"),
        pytest.param(CommandResult(0, "uv", ""), id="one_word"),
        pytest.param(subprocess.TimeoutExpired("uv", 10), id="timeout"),
        pytest.param(OSError("boom"), id="oserror"),
    ],
)
def test_uv_version_is_none_when_the_answer_is_unusable(result: CommandResult | Exception) -> None:
    assert host(Recorder(result)).uv_version() is None


def test_directory_exists_distinguishes_folder_file_and_missing(tmp_path: Path) -> None:
    (tmp_path / "arquivo").write_text("x", encoding="utf-8")
    inspector = host(Recorder(CommandResult(0, "", "")))

    assert inspector.directory_exists(tmp_path) is True
    assert inspector.directory_exists(tmp_path / "arquivo") is False
    assert inspector.directory_exists(tmp_path / "nada") is False
