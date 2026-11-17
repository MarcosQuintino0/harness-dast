"""Proteção de propriedade das pilhas descartáveis das provas crAPI."""

import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from harness_dast.domain.errors import HarnessError
from tests.integration.lab_support import REPO
from tests.integration.oast_cleanup import CRAPI_PROJECT, PROJECT, OastCleanup


@dataclass(frozen=True)
class Inventory:
    """Identidades completas observadas nas duas pilhas."""

    containers: frozenset[str]
    networks: frozenset[str]
    volumes: frozenset[tuple[str, str]]

    def empty(self) -> bool:
        return not (self.containers or self.networks or self.volumes)


class ResourceSafetyError(HarnessError):
    """Inventário inseguro: não derrubar e pedir intervenção humana."""


def docker_runner(env: Mapping[str, str]) -> Callable[[tuple[str, ...]], str]:
    """Executa somente consultas solicitadas pelo inventário, sem expor a saída de erro."""

    def run(args: tuple[str, ...]) -> str:
        executable = shutil.which("docker")
        if executable is None:
            raise ResourceSafetyError("Docker indisponível para inventário; intervenção humana.")
        result = subprocess.run(  # noqa: S603 - argumentos fixos de inventário
            [executable, *args],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=True,
        )
        return result.stdout.strip()

    return run


def inventory(run: Callable[[tuple[str, ...]], str]) -> Inventory:
    """Inclui recursos rotulados e redes/volumes com nomes reservados aos projetos."""
    inspector = OastCleanup(run, "", "", "")
    inspector.capture_stack()
    if (
        inspector.stack_containers is None
        or inspector.stack_networks is None
        or inspector.stack_volumes is None
    ):
        raise ResourceSafetyError("Inventário incompleto; intervenção humana.")
    containers = set(inspector.stack_containers)
    networks = set(inspector.stack_networks)
    volumes = set(inspector.stack_volumes)
    for project in (PROJECT, CRAPI_PROJECT):
        containers.update(inspector._containers(f"name=^/{project}-"))
        for suffix in inspector._project_network_suffixes(project):
            networks.update(inspector._named_networks(project, suffix))
        named = run(("volume", "ls", "-q", "--filter", f"name=^{project}_"))
        for name in named.splitlines():
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
                raise ResourceSafetyError("Nome de volume inválido; intervenção humana.")
            if name.startswith(project + "_"):
                volumes.add(name)
    identities = set()
    for name in volumes:
        created = run(("volume", "inspect", "--format", "{{.CreatedAt}}", name))
        if not created or "\n" in created or created == "<no value>":
            raise ResourceSafetyError("Identidade de volume indisponível; intervenção humana.")
        identities.add((name, created))
    return Inventory(frozenset(containers), frozenset(networks), frozenset(identities))


class ResourceGuard:
    """Recusa subida ocupada e down sem inventário íntegro da própria prova."""

    def __init__(self, inspect: Callable[[], Inventory]) -> None:
        self.inspect = inspect
        self.created: Inventory | None = None

    def _inspect(self) -> Inventory:
        try:
            return self.inspect()
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            TypeError,
            AssertionError,
            HarnessError,
        ) as error:
            raise ResourceSafetyError(
                "Inventário indisponível; intervenção humana necessária."
            ) from error

    def before_up(self) -> None:
        if not self._inspect().empty():
            raise ResourceSafetyError("Projetos ocupados; subida recusada. Intervenção humana.")

    def capture(self) -> Inventory:
        first = self._inspect()
        if first.empty() or first != self._inspect():
            raise ResourceSafetyError(
                "Inventário de subida incompleto ou instável; intervenção humana."
            )
        self.created = first
        return first

    def before_down(self) -> None:
        if self.created is None:
            self._inspect()
            raise ResourceSafetyError("Down recusado: inventário ausente; intervenção humana.")
        if self._inspect() != self.created:
            raise ResourceSafetyError(
                "Down recusado: propriedade não comprovada; intervenção humana."
            )

    def after_down(self) -> None:
        if not self._inspect().empty():
            raise ResourceSafetyError("Recursos restantes após down; intervenção humana.")


def verified_down(guard: ResourceGuard, down: Callable[[], int], records: dict[str, Any]) -> None:
    """Derruba somente inventário próprio e registra verificação final, inclusive na recusa."""
    try:
        guard.before_down()
    except ResourceSafetyError:
        records["down_recusado"] = "propriedade não comprovada; intervenção humana"
        _record_absence(guard, records, propagate=False)
        raise
    try:
        code = down()
        if code != 0:
            raise AssertionError("stack down falhou")
    finally:
        _record_absence(guard, records, propagate=True)


def _record_absence(guard: ResourceGuard, records: dict[str, Any], *, propagate: bool) -> None:
    try:
        guard.after_down()
        records["verificacao_ausencia"] = "sem recursos"
    except ResourceSafetyError:
        records["verificacao_ausencia"] = "restante ou indisponível; intervenção humana"
        if propagate:
            raise
