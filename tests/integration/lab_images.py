"""Constrói as imagens locais do laboratório sem iniciar contêineres."""

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from harness_dast import __version__
from harness_dast.adapters.docker.compose import Runner, run_subprocess
from harness_dast.application.lab_targets import CLINICA_PILOTO
from harness_dast.application.stack import KEY_ENV
from harness_dast.application.stack_images import OWN_SERVICES
from harness_dast.domain.errors import ExternalToolError

PREBUILT_MODE = "HDAST_IT_PREBUILT"
PREBUILD_TIMEOUT = 1800
IMAGE_ENV_KEYS = ("HDAST_ZAP_IMAGE", "HDAST_SCOPE_PROXY_IMAGE")


def build_session_images(
    repo: Path,
    tag: str,
    environ: Mapping[str, str],
    *,
    runner: Runner = run_subprocess,
) -> dict[str, str]:
    """Constrói usando os arquivos da CLI e devolve as referências para a sessão."""
    docker = shutil.which("docker", path=environ.get("PATH", os.defpath))
    if docker is None:
        raise ExternalToolError("Docker indisponível. Instale-o ou desative HDAST_IT_PREBUILT.")
    images = {
        key: f"hdast/{service}:{tag}"
        for key, service in zip(IMAGE_ENV_KEYS, OWN_SERVICES, strict=True)
    }
    env = {
        key: value
        for key, value in environ.items()
        if not key.upper().startswith(("HDAST_", "PILOT_", "COMPOSE_"))
    }
    env.update(images)
    env.update({"HDAST_IMAGE_VERSION": __version__, "COMPOSE_DISABLE_ENV_FILE": "1"})
    # O Compose exige estes valores na interpolação, mesmo sem iniciar serviços.
    env.update(
        dict.fromkeys(
            (KEY_ENV, *CLINICA_PILOTO.credential_env, *CLINICA_PILOTO.inert_env), "lab-build"
        )
    )
    _build(runner, docker, repo, ("compose.yaml",), OWN_SERVICES, env)
    _build(runner, docker, repo / "lab" / "pilot", CLINICA_PILOTO.attached_files, ("pilot",), env)
    return images


def _build(
    runner: Runner,
    docker: str,
    directory: Path,
    files: tuple[str, ...],
    services: tuple[str, ...],
    env: Mapping[str, str],
) -> None:
    command = [docker, "compose"]
    for file in files:
        command.extend(["-f", file])
    command.extend(("build", *services))
    label = ", ".join(services)
    hint = "Confira o Docker e a conexão para baixar as dependências do laboratório."
    try:
        result = runner(command, env, directory, PREBUILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ExternalToolError(
            f"O build de {label} ultrapassou {PREBUILD_TIMEOUT} s.", hint=hint
        ) from None
    except OSError:
        raise ExternalToolError(
            f"Não foi possível iniciar o build de {label}.", hint=hint
        ) from None
    if result.returncode != 0:
        raise ExternalToolError(
            f"O build de {label} falhou com código {result.returncode}.", hint=hint
        )
