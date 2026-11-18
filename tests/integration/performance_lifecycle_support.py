"""Confere ciclo de contêineres de laboratório; não prova semeadura nem dados."""

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from tests.integration.lab_support import CliResult

_PROJECTS = ("hdast", "hdast-pilotrun")
_FORMAT = '{{.ID}}|{{.Label "com.docker.compose.service"}}|{{.State}}'
_ROW = re.compile(r"^([a-f0-9]{12,64})\|([a-z0-9][a-z0-9_-]*)\|([a-z]+)$")
_BASE = {"zap", "zap-gateway", "scope-proxy", "proxy-gateway"}
type Runner = Callable[[str], subprocess.CompletedProcess[str]]


class DownCli(Protocol):
    """Superfície mínima do suporte que executa `stack down`."""

    def run(self, *args: str, timeout: int = 420) -> CliResult: ...


@dataclass(frozen=True)
class Container:
    """Identidade opaca e estado de um contêiner em projeto permitido."""

    project: str
    service: str
    state: str
    id_sha256: str


class LifecycleError(RuntimeError):
    """Estado do ciclo não foi comprovado; a próxima rodada não deve começar."""


def docker_metadata(project: str) -> subprocess.CompletedProcess[str]:
    """Consulta apenas ID, serviço e estado, sem shell nem saída bruta no ledger."""
    if project not in _PROJECTS:
        raise ValueError("projeto inesperado")
    return subprocess.run(  # noqa: S603 - comando fixo, sem shell
        [
            shutil.which("docker") or "docker",
            "ps",
            "-a",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            _FORMAT,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def snapshot(runner: Runner = docker_metadata) -> list[Container]:
    """Consulta os dois projetos; qualquer erro ou linha malformada impede comprovação."""
    containers: list[Container] = []
    for project in _PROJECTS:
        try:
            result = runner(project)
        except subprocess.TimeoutExpired as error:
            raise LifecycleError("docker_timeout") from error
        except OSError as error:
            raise LifecycleError("docker_unavailable") from error
        except UnicodeError as error:
            raise LifecycleError("invalid_metadata") from error
        if result.returncode != 0:
            raise LifecycleError("docker_failed")
        for line in result.stdout.splitlines():
            match = _ROW.fullmatch(line)
            if match is None:
                raise LifecycleError("invalid_metadata")
            ident, service, state = match.groups()
            containers.append(
                Container(project, service, state, hashlib.sha256(ident.encode()).hexdigest())
            )
    if len({item.id_sha256 for item in containers}) != len(containers):
        raise LifecycleError("duplicate_id")
    return containers


def expected_running(items: list[Container], product: str) -> bool:
    """Exige exatamente os serviços do produto, únicos, em execução."""
    if product not in {"vampi", "clinica-piloto"}:
        return False
    expected = {("hdast", service) for service in _BASE}
    expected.add(("hdast", "vampi") if product == "vampi" else ("hdast-pilotrun", "pilot"))
    actual = [(item.project, item.service) for item in items]
    return (
        len(actual) == len(expected)
        and set(actual) == expected
        and all(item.state == "running" for item in items)
    )


class Lifecycle:
    """Registra apenas metadados sanitizados; falhas não liberam o próximo cenário."""

    def __init__(
        self, folder: Path, name: str, product: str, runner: Runner = docker_metadata
    ) -> None:
        folder = folder / "lifecycle"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{name}.json"
        self.data: dict[str, Any] = {
            "product": product,
            "status": "inconclusivo",
            "phases": {},
            "limit": "Somente contêineres: não comprova semeadura ou conteúdo dos dados.",
        }
        self.product = product
        self.runner = runner
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.data, stream, ensure_ascii=False)

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def _check(self, phase: str, *, empty: bool) -> None:
        try:
            items = snapshot(self.runner)
        except LifecycleError as error:
            self.data["phases"][phase] = {"status": "inconclusivo", "reason": str(error)}
            self._save()
            raise
        valid = not items if empty else expected_running(items, self.product)
        self.data["phases"][phase] = {
            "status": "ok" if valid else "inconclusivo",
            "containers": [asdict(item) for item in items],
        }
        self._save()
        if not valid:
            raise LifecycleError(f"{phase}_unexpected_containers")

    def before_up(self) -> None:
        """Exige ausência de contêineres dos dois projetos antes de subir."""
        self._check("before_up", empty=True)

    def after_up(self) -> None:
        """Exige os serviços esperados em execução após a subida."""
        self._check("after_up", empty=False)

    def down(self, cli: DownCli) -> None:
        """Exige encerramento confirmado e ausência de contêineres dos dois projetos."""
        try:
            result = cli.run("stack", "down", timeout=240)
        except (subprocess.TimeoutExpired, OSError) as error:
            self.data["phases"]["down"] = {"status": "inconclusivo", "reason": "down_unavailable"}
            self._save()
            self._check("after_down", empty=True)
            raise LifecycleError("down_unavailable") from error
        self.data["phases"]["down"] = {
            "status": "ok" if result.code == 0 else "inconclusivo",
            "exit_code": result.code,
        }
        self._save()
        self._check("after_down", empty=True)
        if result.code != 0:
            raise LifecycleError("down_failed")
        if self.data["phases"].get("after_up", {}).get("status") == "ok":
            self.data["status"] = "ciclo_containers_confirmado"
        self._save()
