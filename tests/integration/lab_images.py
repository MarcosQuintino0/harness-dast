"""Constrói as imagens locais do laboratório sem iniciar contêineres."""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from harness_dast import __version__
from harness_dast.adapters.docker.compose import Runner, run_subprocess
from harness_dast.application.lab_targets import CLINICA_PILOTO
from harness_dast.application.stack import KEY_ENV
from harness_dast.application.stack_images import OWN_SERVICES
from harness_dast.domain.errors import ConfigError, ExternalToolError, HarnessError

PREBUILT_MODE = "HDAST_IT_PREBUILT"
PREBUILT_TAG = "HDAST_IT_PREBUILT_TAG"
PREBUILD_TIMEOUT = 1800
INSPECT_TIMEOUT = 120
IMAGE_ENV_KEYS = ("HDAST_ZAP_IMAGE", "HDAST_SCOPE_PROXY_IMAGE")
# A Clínica Piloto tem tag fixa no lab/pilot/compose.yaml; só o ZAP e o proxy seguem a sessão.
PILOT_IMAGE = "hdast-clinica-piloto:1.0.0"
TAG_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def session_image_refs(tag: str) -> dict[str, str]:
    """Referências do ZAP e do proxy para a tag da sessão, na ordem de `IMAGE_ENV_KEYS`."""
    return {
        key: f"hdast/{service}:{tag}"
        for key, service in zip(IMAGE_ENV_KEYS, OWN_SERVICES, strict=True)
    }


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
    images = session_image_refs(tag)
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


def prepare_session_images(
    repo: Path,
    environ: Mapping[str, str],
    default_tag: str,
    *,
    runner: Runner = run_subprocess,
) -> dict[str, str]:
    """Reaproveita as imagens da tag `HDAST_IT_PREBUILT_TAG` se existirem; senão, constrói.

    Sem a variável, constrói com `default_tag`. Com ela, o workflow do GitHub carrega as
    imagens do cache e a sessão não reconstrói nada. Uma tag inválida é recusada.
    """
    tag = environ.get(PREBUILT_TAG) or None
    if tag is None:
        return build_session_images(repo, default_tag, environ, runner=runner)
    if TAG_PATTERN.fullmatch(tag) is None:
        raise ConfigError(
            f"A tag {PREBUILT_TAG} é inválida. Use letras, números, ponto, hífen e sublinhado."
        )
    images = session_image_refs(tag)
    if _images_exist(runner, repo, environ, (*images.values(), PILOT_IMAGE)):
        return images
    return build_session_images(repo, tag, environ, runner=runner)


def _images_exist(
    runner: Runner, repo: Path, environ: Mapping[str, str], references: Sequence[str]
) -> bool:
    docker = shutil.which("docker", path=environ.get("PATH", os.defpath))
    if docker is None:
        raise ExternalToolError("Docker indisponível. Instale-o ou desative HDAST_IT_PREBUILT.")
    try:
        result = runner(
            [docker, "image", "inspect", *references], dict(environ), repo, INSPECT_TIMEOUT
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


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


def main(argv: Sequence[str] | None = None) -> int:
    """Prepara as imagens da tag dada e imprime as referências, uma por linha."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("Uso: python -m tests.integration.lab_images TAG\n")
        return 2
    repo = Path(__file__).resolve().parents[2]
    try:
        images = prepare_session_images(repo, {**os.environ, PREBUILT_TAG: args[0]}, args[0])
    except HarnessError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return exc.exit_code
    sys.stdout.writelines(f"{ref}\n" for ref in (*images.values(), PILOT_IMAGE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
