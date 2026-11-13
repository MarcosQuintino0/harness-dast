"""Docker Compose por linha de comando (implementa `ComposeRunner`).

Garantias: nunca usa shell (lista de argumentos), toda chamada tem prazo, o ambiente extra
(chave do ZAP, senhas descartáveis) vai SÓ no ambiente do processo filho e jamais na linha de
comando, e toda falha vira `ExternalToolError` com orientação. A saída bruta do docker não é
repassada (pode conter valores interpolados); só um trecho curto e sem o ambiente extra.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from harness_dast.application.stack_models import ComposeProject, ServiceStatus
from harness_dast.domain.errors import ConfigError, ExternalToolError

STATUS_TIMEOUT_SECONDS = 30
_GRACE_SECONDS = 30
_MAX_DETAIL_CHARS = 300


@dataclass(frozen=True)
class CommandResult:
    """Resultado de um processo.

    Attributes:
        returncode: Código de saída.
        stdout: Saída padrão.
        stderr: Saída de erro.
    """

    returncode: int
    stdout: str
    stderr: str


type Runner = Callable[[list[str], Mapping[str, str], Path, float], CommandResult]
"""Executa (argumentos, ambiente, pasta, prazo) e levanta `subprocess.TimeoutExpired`/`OSError`."""


def default_repo_root() -> Path:
    """Raiz do repositório: `<raiz>/src/harness_dast/adapters/docker/compose.py`.

    Raises:
        ConfigError: Se a raiz calculada não tem `compose.yaml`.
    """
    root = Path(__file__).resolve().parents[4]
    if not (root / "compose.yaml").is_file():
        raise ConfigError(
            "Não encontrei o compose.yaml do repositório.",
            hint="Execute o hdast a partir de uma cópia do repositório (uv run hdast ...).",
        )
    return root


def run_subprocess(
    args: list[str], env: Mapping[str, str], cwd: Path, timeout: float
) -> CommandResult:
    """Executa o processo sem shell e captura a saída."""
    completed = subprocess.run(  # noqa: S603 - argumentos montados aqui, sem shell
        args,
        env=dict(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class DockerComposeCli:
    """Executa `docker compose` para um projeto."""

    def __init__(self, base_env: Mapping[str, str], runner: Runner = run_subprocess) -> None:
        """Cria o adaptador.

        Args:
            base_env: Ambiente herdado pelo processo filho (o docker precisa de PATH, HOME...).
            runner: Execução do processo; injetada nos testes.
        """
        self._base_env = dict(base_env)
        self._runner = runner

    def up(
        self, project: ComposeProject, env: dict[str, str], *, build: bool, timeout_seconds: int
    ) -> None:
        """Sobe o projeto (`up -d --wait --force-recreate`) dentro do prazo."""
        command = [*_prefix(project), "up", "-d", "--wait", "--wait-timeout", str(timeout_seconds)]
        command.append("--force-recreate")
        if build:
            command.append("--build")
        command.extend(project.services)
        self._run(project, command, env, timeout_seconds + _GRACE_SECONDS, "subir")

    def down(self, project: ComposeProject, env: dict[str, str], *, timeout_seconds: int) -> None:
        """Derruba o projeto (`down --remove-orphans`) dentro do prazo."""
        command = [*_prefix(project), "down", "--remove-orphans", "--timeout", "20"]
        self._run(project, command, env, timeout_seconds, "derrubar")

    def status(self, project: ComposeProject, env: dict[str, str]) -> tuple[ServiceStatus, ...]:
        """Lista os contêineres do projeto (`ps --all --format json`)."""
        command = [*_prefix(project), "ps", "--all", "--format", "json"]
        result = self._run(project, command, env, STATUS_TIMEOUT_SECONDS, "consultar")
        return _parse_status(project.name, result.stdout)

    def _run(
        self,
        project: ComposeProject,
        command: list[str],
        env: dict[str, str],
        timeout: float,
        verb: str,
    ) -> CommandResult:
        docker = shutil.which("docker", path=self._base_env.get("PATH", os.defpath))
        if docker is None:
            raise ExternalToolError(
                "O comando docker não foi encontrado.",
                hint="Instale o Docker Desktop e confira se o docker está no PATH.",
            )
        try:
            result = self._runner(
                [docker, *command], {**self._base_env, **env}, Path(project.workdir), timeout
            )
        except subprocess.TimeoutExpired:
            raise ExternalToolError(
                f"O Docker não terminou de {verb} o projeto {project.name} em {int(timeout)} s.",
                hint="Confira o Docker Desktop (docker ps) e rode de novo; o estado foi mantido.",
            ) from None
        except OSError:
            raise ExternalToolError(
                "Não foi possível executar o docker.",
                hint="Confira a instalação do Docker Desktop.",
            ) from None
        if result.returncode != 0:
            raise ExternalToolError(
                f"O docker compose falhou ao {verb} o projeto {project.name}: "
                f"{_detail(result, env)}",
                hint="Confira se o Docker Desktop está em execução (docker info) e os logs "
                "do projeto (docker compose -p NOME logs).",
            )
        return result


def _prefix(project: ComposeProject) -> list[str]:
    command = ["compose", "-p", project.name]
    for file in project.files:
        command.extend(["-f", file])
    for profile in project.profiles:
        command.extend(["--profile", profile])
    return command


def _detail(result: CommandResult, env: Mapping[str, str]) -> str:
    text = " ".join((result.stderr or result.stdout).split())
    for value in env.values():
        if value and len(value) >= 4:
            text = text.replace(value, "***")
    return text[:_MAX_DETAIL_CHARS] or f"código de saída {result.returncode}"


def _parse_status(project: str, stdout: str) -> tuple[ServiceStatus, ...]:
    text = stdout.strip()
    if not text:
        return ()
    try:
        # Versões novas do compose escrevem um objeto por linha; as antigas, uma lista.
        rows = (
            json.loads(text) if text.startswith("[") else [json.loads(x) for x in text.splitlines()]
        )
    except ValueError:
        raise ExternalToolError(
            "A saída do docker compose ps não é JSON.",
            hint="Atualize o Docker Desktop (compose v2.21 ou mais novo).",
        ) from None
    return tuple(
        ServiceStatus(
            project=project,
            service=str(row.get("Service", "")),
            state=str(row.get("State", "")),
            health=str(row.get("Health", "")),
        )
        for row in rows
        if isinstance(row, dict)
    )
