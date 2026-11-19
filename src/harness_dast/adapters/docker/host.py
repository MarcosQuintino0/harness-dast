"""Inspeção da máquina para o `doctor` e operações sobre imagens da pilha.

O diagnóstico só lê a máquina. Apenas `pull_image` solicita um download ao Docker.
"""

import json
import re
import shutil
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from harness_dast.adapters.docker.compose import CommandResult, Runner, default_compose_root
from harness_dast.adapters.docker.compose import run_subprocess as run_process
from harness_dast.application.stack_images import IMAGE_RECOVERY, ImageInfo
from harness_dast.domain.errors import ConfigError, ExternalToolError

DOCKER_TIMEOUT_SECONDS = 20.0
PULL_TIMEOUT_SECONDS = 600.0
UV_TIMEOUT_SECONDS = 10.0
PORT_PROBE_SECONDS = 0.5
_LOOPBACK = "127.0.0.1"
_NO_SUCH_IMAGE = "no such image"
_MAX_COMPOSE_BYTES = 262_144
_IMAGE_DEFAULT = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):-([^{}]+)\}")
_IMAGE_VERSION_FORMAT = '{{json (index .Config.Labels "org.opencontainers.image.version")}}'


class _ImageReference(BaseModel):
    value: str = Field(
        max_length=512,
        pattern=(
            r"^[A-Za-z0-9][A-Za-z0-9_.:-]*(?:/[A-Za-z0-9][A-Za-z0-9_.:-]*)*"
            r"(?:@[A-Za-z0-9_.+-]+:[0-9A-Fa-f]{32,})?$"
        ),
    )


class SystemHost:
    """Inspeciona Docker, imagens, portas, pastas e o `uv` da máquina."""

    def __init__(
        self,
        base_env: Mapping[str, str],
        *,
        runner: Runner = run_process,
        repo_root: Path | None = None,
    ) -> None:
        """Cria o inspetor.

        Args:
            base_env: Ambiente herdado pelos processos filhos (PATH, HOME...).
            runner: Execução de processo; injetada nos testes.
            repo_root: Pasta do `compose.yaml`; `None` usa o localizador da pilha.
        """
        self._env = dict(base_env)
        self._runner = runner
        self._repo_root = repo_root

    def docker_version(self) -> str:
        """Versão do servidor Docker que respondeu (veja `HostInspector.docker_version`)."""
        result = self._docker(["version", "--format", "{{.Server.Version}}"])
        version = result.stdout.strip()
        if result.returncode != 0 or not version:
            raise ExternalToolError(
                "O Docker não respondeu.",
                hint="Inicie o Docker Desktop ou o serviço do Docker e rode o doctor de novo.",
            )
        return version

    def compose_images(
        self, services: tuple[str, ...], overrides: Mapping[str, str]
    ) -> dict[str, str]:
        """Resolve literais e referências `${VAR:-padrão}` do Compose para os serviços."""
        root = self._repo_root if self._repo_root is not None else default_compose_root()
        compose = root / "compose.yaml"
        try:
            if compose.stat().st_size > _MAX_COMPOSE_BYTES:
                raise ConfigError(
                    "O compose.yaml da pilha é grande demais.",
                    hint="Restaure o compose.yaml original.",
                )
            data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            raise ConfigError(
                "Não consegui ler o compose.yaml da pilha.",
                hint="Confira o pacote instalado ou restaure o compose.yaml do clone.",
            ) from None
        declared = data.get("services") if isinstance(data, dict) else None
        if not isinstance(declared, dict):
            raise ConfigError(
                "O compose.yaml da pilha não tem a seção services.",
                hint="Restaure o compose.yaml original.",
            )
        env = {**self._env, **overrides}
        found: dict[str, str] = {}
        for name in services:
            service = declared.get(name)
            image = service.get("image") if isinstance(service, dict) else None
            if isinstance(image, str):
                found[name] = _resolve_image(name, image, env)
        return found

    def inspect_image(self, reference: str) -> ImageInfo | None:
        """Consulta a existência da imagem local e seu rótulo OCI de versão."""
        result = self._docker(["image", "inspect", "--format", _IMAGE_VERSION_FORMAT, reference])
        if result.returncode == 0:
            try:
                value = json.loads(result.stdout)
                return ImageInfo.model_validate({"version": None if value == "" else value})
            except ValueError:
                raise ExternalToolError(
                    "O Docker devolveu metadados inválidos para uma imagem da pilha.",
                    hint=IMAGE_RECOVERY,
                ) from None
        if _NO_SUCH_IMAGE in (result.stderr + result.stdout).lower():
            return None
        raise ExternalToolError(
            "O Docker não conseguiu consultar as imagens.",
            hint="Confira se o Docker Desktop está em execução (docker info).",
        )

    def pull_image(self, reference: str) -> None:
        """Baixa a referência pelo Docker com prazo e sem repassar a saída bruta."""
        result = self._docker(["image", "pull", reference], timeout=PULL_TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise ExternalToolError(
                f"O Docker não conseguiu baixar a imagem {reference}.",
                hint="Confira se a imagem foi publicada, o acesso ao registro e o espaço em disco.",
            )

    def port_is_free(self, port: int) -> bool:
        """Diz se a porta de 127.0.0.1 está livre (veja `HostInspector.port_is_free`)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(PORT_PROBE_SECONDS)
            if probe.connect_ex((_LOOPBACK, port)) == 0:
                return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as binder:
            try:
                binder.bind((_LOOPBACK, port))
            except OSError:
                return False
        return True

    def uv_version(self) -> str | None:
        """Versão do `uv` no PATH, ou `None` (veja `HostInspector.uv_version`)."""
        uv = shutil.which("uv", path=self._env.get("PATH"))
        if uv is None:
            return None
        try:
            result = self._runner([uv, "--version"], self._env, Path.cwd(), UV_TIMEOUT_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            return None
        words = result.stdout.split()
        if result.returncode != 0 or len(words) < 2:
            return None
        return words[1]

    def directory_exists(self, path: Path) -> bool:
        """Diz se `path` é uma pasta existente."""
        return path.is_dir()

    def _docker(self, args: list[str], *, timeout: float = DOCKER_TIMEOUT_SECONDS) -> CommandResult:
        docker = shutil.which("docker", path=self._env.get("PATH"))
        if docker is None:
            raise ExternalToolError(
                "O comando docker não foi encontrado.",
                hint="Instale o Docker Desktop e confira se o docker está no PATH.",
            )
        try:
            return self._runner([docker, *args], self._env, Path.cwd(), timeout)
        except subprocess.TimeoutExpired:
            raise ExternalToolError(
                f"O Docker não respondeu em {int(timeout)} s.",
                hint="O Docker Desktop pode estar travado: reinicie-o e rode o doctor de novo.",
            ) from None
        except OSError:
            raise ExternalToolError(
                "Não foi possível executar o docker.",
                hint="Confira a instalação do Docker Desktop.",
            ) from None


def _resolve_image(name: str, expression: str, env: Mapping[str, str]) -> str:
    default = _IMAGE_DEFAULT.fullmatch(expression)
    value = (env.get(default[1]) or default[2]) if default else expression
    try:
        return _ImageReference(value=value).value
    except ValidationError:
        raise ConfigError(
            f"A referência da imagem do serviço {name} é inválida.",
            hint="Confira a variável de ambiente da imagem e o compose.yaml.",
        ) from None
