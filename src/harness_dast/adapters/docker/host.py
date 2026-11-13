"""Inspeção da máquina para o `doctor` (implementa `HostInspector`).

Só lê: `docker version`, `docker image inspect`, `uv --version`, uma tentativa de conexão e de
`bind` em 127.0.0.1 e a leitura do `compose.yaml`. Nunca usa shell (lista de argumentos), toda
chamada tem prazo e nada é enviado a rede alguma além de 127.0.0.1.
"""

import shutil
import socket
import subprocess
from collections.abc import Mapping
from pathlib import Path

import yaml

from harness_dast.adapters.docker.compose import CommandResult, Runner, default_repo_root
from harness_dast.adapters.docker.compose import run_subprocess as run_process
from harness_dast.domain.errors import ConfigError, ExternalToolError

DOCKER_TIMEOUT_SECONDS = 20.0
UV_TIMEOUT_SECONDS = 10.0
PORT_PROBE_SECONDS = 0.5
_LOOPBACK = "127.0.0.1"
_NO_SUCH_IMAGE = "no such image"
_MAX_COMPOSE_BYTES = 262_144


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
            repo_root: Raiz do repositório (onde fica o `compose.yaml`); `None` calcula a
                partir deste pacote.
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
                hint="Abra o Docker Desktop, espere ele ficar pronto e rode o doctor de novo.",
            )
        return version

    def compose_images(self, services: tuple[str, ...]) -> tuple[str, ...]:
        """Imagens do `compose.yaml` para os serviços (veja `HostInspector.compose_images`)."""
        root = self._repo_root if self._repo_root is not None else default_repo_root()
        compose = root / "compose.yaml"
        try:
            if compose.stat().st_size > _MAX_COMPOSE_BYTES:
                raise ConfigError(
                    "O compose.yaml do repositório é grande demais.",
                    hint="Restaure o compose.yaml original.",
                )
            data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            raise ConfigError(
                "Não consegui ler o compose.yaml do repositório.",
                hint="Rode o hdast a partir de uma cópia íntegra do repositório.",
            ) from None
        declared = data.get("services") if isinstance(data, dict) else None
        if not isinstance(declared, dict):
            raise ConfigError(
                "O compose.yaml do repositório não tem a seção services.",
                hint="Restaure o compose.yaml original.",
            )
        found: list[str] = []
        for name in services:
            service = declared.get(name)
            image = service.get("image") if isinstance(service, dict) else None
            if isinstance(image, str) and image not in found:
                found.append(image)
        return tuple(found)

    def image_present(self, reference: str) -> bool:
        """Diz se a imagem está no Docker local (veja `HostInspector.image_present`)."""
        result = self._docker(["image", "inspect", "--format", "{{.Id}}", reference])
        if result.returncode == 0:
            return True
        if _NO_SUCH_IMAGE in (result.stderr + result.stdout).lower():
            return False
        raise ExternalToolError(
            "O Docker não conseguiu consultar as imagens.",
            hint="Confira se o Docker Desktop está em execução (docker info).",
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

    def _docker(self, args: list[str]) -> CommandResult:
        docker = shutil.which("docker", path=self._env.get("PATH"))
        if docker is None:
            raise ExternalToolError(
                "O comando docker não foi encontrado.",
                hint="Instale o Docker Desktop e confira se o docker está no PATH.",
            )
        try:
            return self._runner([docker, *args], self._env, Path.cwd(), DOCKER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise ExternalToolError(
                f"O Docker não respondeu em {int(DOCKER_TIMEOUT_SECONDS)} s.",
                hint="O Docker Desktop pode estar travado: reinicie-o e rode o doctor de novo.",
            ) from None
        except OSError:
            raise ExternalToolError(
                "Não foi possível executar o docker.",
                hint="Confira a instalação do Docker Desktop.",
            ) from None
