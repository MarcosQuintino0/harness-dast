"""Docker Compose por linha de comando (implementa `ComposeRunner`).

Garantias: nunca usa shell (lista de argumentos), toda chamada tem prazo, o ambiente extra
(chave do ZAP, senhas descartáveis) vai SÓ no ambiente do processo filho e jamais na linha de
comando, e toda falha vira `ExternalToolError` com orientação. A saída bruta do docker não é
repassada, pois pode conter credenciais herdadas ou transformadas.
"""

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from harness_dast.application.stack_models import ComposeProject, OneShotResult, ServiceStatus
from harness_dast.domain.errors import ConfigError, ExternalToolError

STATUS_TIMEOUT_SECONDS = 30
_GRACE_SECONDS = 30
KILL_SECONDS = 30
"""Prazo do `docker rm -f` que mata o contêiner de uso único depois de estourar o prazo dele."""
_CONTAINER_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,62}")
BUILD_SECONDS = 600
"""Prazo extra do processo quando o `up` reconstrói imagens (`--build`).

O `--wait-timeout` só conta a espera pela saúde dos contêineres. O build roda antes.
"""


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


def default_compose_root(
    *,
    package: Path | None = None,
    is_file: Callable[[Path], bool] = Path.is_file,
) -> Path:
    """Localiza o Compose do clone editável ou o arquivo da instalação."""
    package = Path(__file__).resolve().parents[2] if package is None else package
    root = package.parent.parent
    if (
        package.parent.name == "src"
        and is_file(root / "pyproject.toml")
        and is_file(root / "compose.yaml")
    ):
        return root
    if is_file(package / "compose.yaml"):
        return package
    raise ConfigError(
        "Não encontrei o compose.yaml da pilha.",
        hint="Reinstale o wheel da release ou restaure o compose.yaml do clone.",
    )


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

    def build(
        self, project: ComposeProject, env: dict[str, str], services: tuple[str, ...]
    ) -> None:
        """Constrói os serviços indicados sem iniciar contêineres."""
        command = [*_prefix(project), "build", *services]
        self._run(project, command, env, BUILD_SECONDS, "construir")

    def up(
        self,
        project: ComposeProject,
        env: dict[str, str],
        *,
        build: bool | None,
        timeout_seconds: int,
    ) -> None:
        """Sobe o projeto (`up -d --wait --force-recreate`) dentro do prazo."""
        command = [*_prefix(project), "up", "-d", "--wait", "--wait-timeout", str(timeout_seconds)]
        command.append("--force-recreate")
        if build is True:
            command.append("--build")
        if build is False:
            command.append("--no-build")
        command.extend(project.services)
        allowance = BUILD_SECONDS if build else 0
        self._run(project, command, env, timeout_seconds + _GRACE_SECONDS + allowance, "subir")

    def down(self, project: ComposeProject, env: dict[str, str], *, timeout_seconds: int) -> None:
        """Derruba o projeto (`down --remove-orphans`) dentro do prazo."""
        command = [*_prefix(project), "down", "--remove-orphans", "--timeout", "20"]
        if project.remove_volumes:
            command.append("--volumes")
        self._run(project, command, env, timeout_seconds, "derrubar")

    def run_once(
        self,
        project: ComposeProject,
        env: dict[str, str],
        service: str,
        args: tuple[str, ...],
        *,
        container_name: str,
        timeout_seconds: int,
        mounts: tuple[str, ...] = (),
    ) -> OneShotResult:
        """Roda o serviço uma vez (`run --rm -T --no-deps`) dentro do prazo.

        A entrada padrão do processo do docker é `/dev/null` (`run_subprocess`) e `-T` evita o
        terminal: com a entrada aberta o Nuclei travou na partida (spike, ADR 0122). Ao estourar o
        prazo, `docker rm -f` mata e remove o contêiner pelo nome, e só então o erro sobe.
        """
        if not _CONTAINER_NAME.fullmatch(container_name):
            raise ConfigError(
                "Nome de contêiner inválido para a execução única.",
                hint="Use minúsculas, dígitos, ponto, hífen ou sublinhado, até 63 caracteres.",
            )
        command = [*_prefix(project), "run", "--rm", "-T", "--no-deps", "--name", container_name]
        for mount in mounts:
            if not mount.endswith(":ro") or mount.startswith("-") or not mount.isprintable():
                raise ConfigError(
                    "Montagem recusada na execução única: só leitura (origem:destino:ro).",
                    hint="Monte os arquivos do Nuclei somente leitura.",
                )
            command.extend(["-v", mount])
        command.extend([service, *args])
        docker = self._docker()
        full_env = {**self._base_env, **env}
        try:
            result = self._runner(
                [docker, *command],
                full_env,
                Path(project.workdir),
                timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            self._kill_container(docker, project, full_env, container_name)
            raise ExternalToolError(
                f"O contêiner {service} passou do prazo de {timeout_seconds} s e foi encerrado.",
                hint="Reduza a quantidade de modelos ou aumente o prazo; o contêiner foi removido.",
            ) from None
        except OSError:
            raise ExternalToolError(
                "Não foi possível executar o docker.",
                hint="Confira a instalação do Docker Desktop.",
            ) from None
        return OneShotResult(exit_code=result.returncode, stdout=result.stdout)

    def _kill_container(
        self, docker: str, project: ComposeProject, env: Mapping[str, str], name: str
    ) -> None:
        try:
            result = self._runner(
                [docker, "rm", "-f", name], env, Path(project.workdir), KILL_SECONDS
            )
        except (subprocess.TimeoutExpired, OSError):
            result = CommandResult(1, "", "")
        # `rm -f` de um contêiner que já saiu devolve erro de "não existe": é o resultado certo.
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise ExternalToolError(
                f"O contêiner {name} passou do prazo e não pôde ser encerrado.",
                hint=f"Rode docker rm -f {name} agora.",
            )

    def _docker(self) -> str:
        docker = shutil.which("docker", path=self._base_env.get("PATH", os.defpath))
        if docker is None:
            raise ExternalToolError(
                "O comando docker não foi encontrado.",
                hint="Instale o Docker Desktop e confira se o docker está no PATH.",
            )
        return docker

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
        docker = self._docker()
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
            hint = (
                "Confira o Docker, a conexão para baixar dependências e rode uv sync."
                if verb == "construir"
                else "Confira se o Docker está em execução (docker info) e os logs "
                "do projeto (docker compose -p NOME logs)."
            )
            raise ExternalToolError(
                f"O docker compose falhou ao {verb} o projeto {project.name}: "
                f"código de saída {result.returncode}.",
                hint=hint,
            )
        return result


def _prefix(project: ComposeProject) -> list[str]:
    command = ["compose", "-p", project.name]
    for file in project.files:
        command.extend(["-f", file])
    for profile in project.profiles:
        command.extend(["--profile", profile])
    return command


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
