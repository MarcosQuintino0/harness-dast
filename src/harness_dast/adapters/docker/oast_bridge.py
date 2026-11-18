"""Inspeção local, somente leitura, da topologia e do Callback da ponte OAST."""

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness_dast.application.stack_models import StackState
from harness_dast.domain.errors import ConfigError


class ContainerId(BaseModel):
    """ID validado, sem argumentos ou texto arbitrário da saída externa."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    value: str = Field(pattern=r"^[0-9a-f]{12,64}$")


def run_docker(args: list[str], environ: Mapping[str, str]) -> tuple[int, str] | None:
    """Executa inspeção limitada, sem revelar saída de erro."""
    docker = shutil.which("docker", path=environ.get("PATH", os.defpath))
    if docker is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - argumentos fixos e validados pelo estado
            [docker, *args],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
            check=False,
            env=dict(environ),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.returncode, result.stdout.strip()


class DockerOastBridge:
    """Consulta contêineres em execução sem consultar o alvo nem expor saídas do Docker."""

    def __init__(
        self,
        load_state: Callable[[], StackState | None],
        environ: Mapping[str, str],
        runner: Callable[[list[str], Mapping[str, str]], tuple[int, str] | None] = run_docker,
    ) -> None:
        """Recebe a leitura do estado gerenciado; não consulta Docker até `inspect`."""
        self._load_state = load_state
        self._runner = runner
        self._environ = dict(environ)

    def inspect(self) -> bool | None:
        """Confere processos e redes; `None` indica falha de inspeção, não sucesso."""
        try:
            state = self._load_state()
        except ConfigError:
            return None
        if state is None or state.lab_target != "crapi" or len(state.projects) < 2:
            return False
        main, target = state.projects[0], state.projects[1]
        network = f"{main.name}_oast_net"
        gateway = self._container(main.name, "oast-gateway", network)
        workshop = self._container(target.name, "crapi-workshop", network)
        zap_side = self._container(main.name, "oast-gateway", f"{main.name}_zap_net")
        if None in (gateway, workshop, zap_side):
            return None
        return bool(gateway and workshop and gateway == zap_side)

    def callback(self) -> bool | None:
        """Tenta conexão TCP do gateway ao Callback, sem enviar HTTP ao alvo."""
        try:
            state = self._load_state()
        except ConfigError:
            return None
        if state is None or not state.projects:
            return False
        main = state.projects[0]
        gateway = self._container(main.name, "oast-gateway", f"{main.name}_oast_net")
        if gateway is None:
            return None
        if not gateway:
            return False
        result = self._run(
            ["exec", gateway, "socat", "-T", "2", "STDIN", "TCP:zap:8090,connect-timeout=2"]
        )
        return None if result is None else result[0] == 0

    def _run(self, args: list[str]) -> tuple[int, str] | None:
        return self._runner(args, self._environ)

    def _container(self, project: str, service: str, network: str) -> str | None:
        result = self._run(
            [
                "ps",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--filter",
                f"network={network}",
                "--format",
                "{{.ID}}",
            ]
        )
        if result is None or result[0] != 0:
            return None
        rows = result[1].splitlines()
        if not rows:
            return ""
        if len(rows) != 1:
            return None
        try:
            return ContainerId(value=rows[0]).value
        except ValidationError:
            return None
