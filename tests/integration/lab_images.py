"""Constrói as imagens locais do laboratório sem iniciar contêineres."""

import hashlib
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
PILOT_REPOSITORY = "hdast-clinica-piloto"
PILOT_IMAGE = f"{PILOT_REPOSITORY}:1.0.0"
# Insumos copiados pelos Dockerfiles do proxy, do ZAP e da Clínica (contextos `.`, `docker/zap`
# e `lab/pilot`). Um teste confere que todo `COPY` está coberto por esta lista.
INPUT_FILES = ("README.md", "pyproject.toml", "uv.lock", "compose.yaml")
INPUT_DIRS = ("src", "docker", "lab/pilot")
SKIPPED_DIRS = frozenset({"__pycache__", "target", ".pytest_cache", ".mypy_cache"})
IDENTITY_PREFIX = "inputs-"
TAG_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def _input_files(repo: Path) -> list[str]:
    found = {name for name in INPUT_FILES if (repo / name).is_file()}
    for directory in INPUT_DIRS:
        for root, dirs, files in os.walk(repo / directory):
            dirs[:] = [name for name in dirs if name not in SKIPPED_DIRS]
            found.update(
                Path(root, name).relative_to(repo).as_posix()
                for name in files
                if not name.endswith(".pyc")
            )
    return sorted(found)


def inputs_hash(repo: Path) -> str:
    """Hash dos arquivos que os builds copiam; é a identidade das imagens do checkout.

    Usa os bytes reais, sem converter fim de linha: o Docker copia os bytes como estão, e um
    script com CRLF é outra imagem. No Windows o valor pode diferir do CI (Linux, checkout em
    LF); isso é aceitável, porque o cache só é usado no CI.
    """
    digest = hashlib.sha256()
    for relative in _input_files(repo):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update((repo / relative).read_bytes() + b"\0")
    return digest.hexdigest()


def identity_refs(identity: str) -> tuple[str, str, str]:
    """Referências de identidade do ZAP, do proxy e da Clínica, nessa ordem."""
    zap, proxy = (f"hdast/{service}:{identity}" for service in OWN_SERVICES)
    return zap, proxy, f"{PILOT_REPOSITORY}:{identity}"


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
    imagens do cache e a sessão não reconstrói nada. O reuso exige que as três imagens
    (ZAP, proxy e Clínica) tragam a tag de identidade `inputs-<hash>` do checkout atual e
    sejam a mesma imagem da tag da sessão; se faltar ou divergir, reconstrói e avisa.
    Uma tag inválida é recusada.
    """
    tag = environ.get(PREBUILT_TAG) or None
    identity = f"{IDENTITY_PREFIX}{inputs_hash(repo)}"
    if tag is not None:
        if TAG_PATTERN.fullmatch(tag) is None:
            raise ConfigError(
                f"A tag {PREBUILT_TAG} é inválida. Use letras, números, ponto, hífen e sublinhado."
            )
        images = session_image_refs(tag)
        if _identity_matches(runner, repo, environ, images, identity):
            return images
        sys.stderr.write(
            f"As imagens da tag {tag} faltam ou não vêm deste checkout ({identity[:20]}...). "
            "Reconstruindo.\n"
        )
    images = build_session_images(repo, tag or default_tag, environ, runner=runner)
    _tag_identity(runner, repo, environ, images, identity)
    return images


def _docker(environ: Mapping[str, str]) -> str:
    docker = shutil.which("docker", path=environ.get("PATH", os.defpath))
    if docker is None:
        raise ExternalToolError("Docker indisponível. Instale-o ou desative HDAST_IT_PREBUILT.")
    return docker


def _identity_matches(
    runner: Runner,
    repo: Path,
    environ: Mapping[str, str],
    images: Mapping[str, str],
    identity: str,
) -> bool:
    """Confere, pelo Id da imagem, que as três tags da sessão são as do checkout."""
    named = (*images.values(), PILOT_IMAGE)
    marked = identity_refs(identity)
    command = [_docker(environ), "image", "inspect", "--format", "{{.Id}}", *named, *marked]
    try:
        result = runner(command, dict(environ), repo, INSPECT_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return False
    ids = result.stdout.split()
    return result.returncode == 0 and len(ids) == 6 and ids[:3] == ids[3:]


def _tag_identity(
    runner: Runner,
    repo: Path,
    environ: Mapping[str, str],
    images: Mapping[str, str],
    identity: str,
) -> None:
    docker = _docker(environ)
    for source, target in zip(
        (*images.values(), PILOT_IMAGE), identity_refs(identity), strict=True
    ):
        try:
            result = runner([docker, "tag", source, target], dict(environ), repo, INSPECT_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            raise ExternalToolError(f"Não foi possível marcar a imagem {source}.") from None
        if result.returncode != 0:
            raise ExternalToolError(
                f"A marcação de identidade de {source} falhou com código {result.returncode}."
            )


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
    """Imprime a chave dos insumos (`--chave`) ou prepara as imagens da tag dada."""
    args = list(sys.argv[1:] if argv is None else argv)
    repo = Path(__file__).resolve().parents[2]
    if args == ["--chave"]:
        sys.stdout.write(inputs_hash(repo) + "\n")
        return 0
    if len(args) != 1:
        sys.stderr.write("Uso: python -m tests.integration.lab_images --chave | TAG\n")
        return 2
    try:
        images = prepare_session_images(repo, {**os.environ, PREBUILT_TAG: args[0]}, args[0])
    except HarnessError as exc:
        sys.stderr.write(f"{exc.message}\n")
        return exc.exit_code
    identity = f"{IDENTITY_PREFIX}{inputs_hash(repo)}"
    refs = (*images.values(), PILOT_IMAGE, *identity_refs(identity))
    sys.stdout.writelines(f"{ref}\n" for ref in refs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
