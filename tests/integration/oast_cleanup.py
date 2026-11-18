"""Reconcilia recursos da prova OAST por etiquetas e nomes, sem tocar em alheios.

O módulo mantém a reconciliação e as verificações finais juntas para que todos os erros da
mesma prova componham um único resultado sanitizado, mesmo com falhas independentes.
"""

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from harness_dast.domain.errors import HarnessError

Runner = Callable[[tuple[str, ...]], str]
OWNER_LABEL = "io.hdast.oast.owner"
_SUFFIX = os.environ.get("HDAST_IT_STACK_SUFFIX") or "-codex"
PROJECT = "hdast" + _SUFFIX
CRAPI_PROJECT = "hdast-crapi" + _SUFFIX
FAILURES = (
    OSError,
    subprocess.SubprocessError,
    ValueError,
    TypeError,
    AssertionError,
    HarnessError,
)


@dataclass
class CleanupResult:
    """Erros sanitizados e autorização de segurança para derrubar a pilha."""

    errors: list[str] = field(default_factory=list)
    unsafe: bool = False


class OastCleanup:
    """Reconstroi a situação mesmo quando a criação expirou antes de responder."""

    def __init__(self, run: Runner, owner: str, network: str, client: str) -> None:
        self.run = run
        self.owner = owner
        self.network = network
        self.client = client
        self.gateway_intended = False
        self.client_intended = False
        self.workshop_intended = False
        self.managed_bridge = False
        self.workshop_before: set[str] = set()
        self.stack_containers: set[str] | None = None
        self.stack_networks: set[str] | None = None
        self.stack_volumes: set[str] | None = None
        self.result = CleanupResult()

    def _attempt(
        self, name: str, operation: Callable[[], object], *, ownership: bool = False
    ) -> None:
        try:
            operation()
        except FAILURES:
            self.result.errors.append(name)
            if ownership:
                self.result.unsafe = True

    def _ids(self, *args: str) -> list[str]:
        values = self.run(tuple(args)).splitlines()
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in values):
            raise ValueError("identificador Docker inválido")
        return values

    def _network_id(self) -> str | None:
        found = self._ids("network", "ls", "-q", "--no-trunc", "--filter", f"name=^{self.network}$")
        if len(found) > 1:
            raise ValueError("rede ambígua")
        if not found:
            return None
        owner = self.run(
            ("network", "inspect", "--format", '{{index .Labels "io.hdast.oast.owner"}}', found[0])
        )
        if owner != self.owner:
            raise ValueError("rede não pertence à prova")
        project = self.run(
            (
                "network",
                "inspect",
                "--format",
                '{{index .Labels "com.docker.compose.project"}}',
                found[0],
            )
        )
        if project != PROJECT:
            raise ValueError("rede não pertence ao projeto exclusivo")
        return found[0]

    def _containers(self, *filters: str) -> list[str]:
        args = ["ps", "-aq", "--no-trunc"]
        for value in filters:
            args.extend(("--filter", value))
        return self._ids(*args)

    def _owned(self, container: str) -> bool:
        value = self.run(
            (
                "container",
                "inspect",
                "--format",
                '{{index .Config.Labels "io.hdast.oast.owner"}}',
                container,
            )
        )
        return value == self.owner

    def _remove_containers(self, name: str, containers: list[str]) -> None:
        for container in containers:
            self._attempt(
                name + "_propriedade",
                partial(self._remove_one, name, container),
                ownership=True,
            )

    def _remove_one(self, name: str, container: str) -> None:
        if not self._owned(container):
            raise ValueError("contêiner não pertence à prova")
        self._attempt(name + "_stop", lambda: self.run(("stop", "-t", "1", container)))
        self._attempt(name + "_rm", lambda: self.run(("rm", container)))

    def _client(self) -> None:
        containers = self._containers(f"name=^/{self.client}$")
        self._remove_containers("cliente", containers)

    def _gateway(self) -> None:
        containers = self._containers(
            f"label=com.docker.compose.project={PROJECT}",
            "label=com.docker.compose.service=oast-gateway",
        )
        self._remove_containers("gateway", containers)

    def _workshop(self) -> None:
        network_id = self._network_id()
        if network_id is None:
            return
        raw = self.run(("network", "inspect", "--format", "{{json .Containers}}", network_id))
        members = json.loads(raw)
        if members is None:
            return
        if not isinstance(members, dict):
            raise TypeError("membros da rede inválidos")
        workshops = self._containers(
            f"label=com.docker.compose.project={CRAPI_PROJECT}",
            "label=com.docker.compose.service=crapi-workshop",
        )
        for container in workshops:
            if container not in members:
                continue
            self._attempt(
                "workshop_propriedade",
                partial(self._disconnect_workshop, network_id, container),
                ownership=True,
            )

    def _disconnect_workshop(self, network_id: str, container: str) -> None:
        if not self._owned(container):
            raise ValueError("workshop não pertence à prova")
        self._attempt(
            "workshop_disconnect",
            lambda: self.run(("network", "disconnect", network_id, container)),
        )

    def _network(self) -> None:
        network_id = self._network_id()
        if network_id is not None:
            self._attempt("rede_rm", lambda: self.run(("network", "rm", network_id)))

    def _verify_network_absent(self) -> None:
        if self._ids("network", "ls", "-q", "--no-trunc", "--filter", f"name=^{self.network}$"):
            raise ValueError("rede da prova ainda existe")

    def _verify_client_absent(self) -> None:
        if self._containers(f"name=^/{self.client}$"):
            raise ValueError("cliente da prova ainda existe")

    def _verify_gateway_absent(self) -> None:
        if self._containers(
            f"label=com.docker.compose.project={PROJECT}",
            "label=com.docker.compose.service=oast-gateway",
        ):
            raise ValueError("gateway ainda existe")

    def _verify_oast(self, prefix: str) -> None:
        self._attempt(prefix + "_rede", self._verify_network_absent)
        self._attempt(prefix + "_cliente", self._verify_client_absent)
        self._attempt(prefix + "_gateway", self._verify_gateway_absent)

    def close(self) -> CleanupResult:
        """Tenta todas as etapas independentes e registra erros sem dados externos."""
        if self.workshop_intended:
            self._attempt("workshop_inspect", self._workshop, ownership=True)
        if self.client_intended:
            self._attempt("cliente_inspect", self._client, ownership=True)
        if self.gateway_intended:
            self._attempt("gateway_inspect", self._gateway, ownership=True)
            self._attempt("rede_inspect", self._network, ownership=True)
            self._verify_oast("oast_restante")
        return self.result

    def verify_projects_owned(self) -> None:
        """Recusa derrubar projetos que ganharam serviços não reconhecidos."""
        if (
            self.stack_containers is None
            or self.stack_networks is None
            or self.stack_volumes is None
        ):
            raise ValueError("inventário confiável ausente; requer intervenção humana")
        allowed = {
            PROJECT: {
                "zap",
                "zap-gateway",
                "proxy-gateway",
                "scope-proxy",
                "vampi",
                "vampi-tls",
                "oast-gateway",
            },
            CRAPI_PROJECT: {
                "crapi-identity",
                "crapi-community",
                "crapi-workshop",
                "crapi-web",
                "postgresdb",
                "mongodb",
                "mailhog",
                "api.mypremiumdealership.com",
            },
        }
        for project, services in allowed.items():
            for container in self._containers(f"label=com.docker.compose.project={project}"):
                self._verify_stack_container(container, services)
            self._verify_stack_storage(project)

    def _verify_stack_container(self, container: str, services: set[str]) -> None:
        service = self.run(
            (
                "container",
                "inspect",
                "--format",
                '{{index .Config.Labels "com.docker.compose.service"}}',
                container,
            )
        )
        if service not in services:
            raise ValueError("serviço não reconhecido no projeto")
        if (
            self.stack_containers is not None
            and container not in self.stack_containers
            and not (service in {"oast-gateway", "crapi-workshop"} and self._owned(container))
        ):
            raise ValueError("contêiner não registrado na pilha")
        if service == "oast-gateway" and not self.managed_bridge and not self._owned(container):
            raise ValueError("gateway não pertence à prova")
        if (
            service == "crapi-workshop"
            and self.workshop_intended
            and container not in self.workshop_before
            and not self._owned(container)
        ):
            raise ValueError("workshop não pertence à prova")

    def _verify_stack_storage(self, project: str) -> None:
        if self.stack_networks is not None:
            added = self._project_networks(project) - self.stack_networks
            if added:
                owned_oast = self._network_id() if self.gateway_intended else None
                if added != {owned_oast}:
                    raise ValueError("rede não registrada na pilha")
            for suffix in self._project_network_suffixes(project):
                if not set(self._named_networks(project, suffix)) <= self.stack_networks:
                    raise ValueError("rede nomeada não registrada na pilha")
        if (
            self.stack_volumes is not None
            and not self._project_volumes(project) <= self.stack_volumes
        ):
            raise ValueError("volume não registrado na pilha")

    def capture_stack(self) -> None:
        """Registra IDs existentes antes de criar o overlay ou recriar o workshop."""
        found: set[str] = set()
        networks: set[str] = set()
        volumes: set[str] = set()
        for project in (PROJECT, CRAPI_PROJECT):
            found.update(self._containers(f"label=com.docker.compose.project={project}"))
            networks.update(self._project_networks(project))
            volumes.update(self._project_volumes(project))
        self.stack_containers = found
        self.stack_networks = networks
        self.stack_volumes = volumes

    def _project_networks(self, project: str) -> set[str]:
        return set(
            self._ids(
                "network",
                "ls",
                "-q",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={project}",
            )
        )

    def _project_volumes(self, project: str) -> set[str]:
        values = self.run(
            ("volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}")
        ).splitlines()
        if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name) for name in values):
            raise ValueError("nome de volume inválido")
        return set(values)

    def verify_final(self) -> None:
        """Confere a rede nomeada e ambos os projetos, mesmo após erro anterior."""
        if self.gateway_intended:
            self._attempt("rede_final_inspect", self._network, ownership=True)
            self._verify_oast("oast_final_restante")
        for project in (PROJECT, CRAPI_PROJECT):
            self._verify_project(project)

    def _verify_project(self, project: str) -> None:
        label = f"label=com.docker.compose.project={project}"
        self._attempt(
            project + "_containers_restantes", lambda: self._assert_empty(self._containers(label))
        )
        self._attempt(
            project + "_redes_restantes",
            lambda: self._assert_empty(
                self._ids("network", "ls", "-q", "--no-trunc", "--filter", label)
            ),
        )
        self._attempt(
            project + "_volumes_restantes",
            lambda: self._assert_empty(self.run(("volume", "ls", "-q", "--filter", label))),
        )
        for suffix in self._project_network_suffixes(project):
            self._attempt(
                project + "_" + suffix + "_restante",
                partial(self._verify_named_network, project, suffix),
            )

    def _verify_named_network(self, project: str, suffix: str) -> None:
        self._assert_empty(self._named_networks(project, suffix))

    def _named_networks(self, project: str, suffix: str) -> list[str]:
        return self._ids(
            "network", "ls", "-q", "--no-trunc", "--filter", f"name=^{project}_{suffix}$"
        )

    @staticmethod
    def _project_network_suffixes(project: str) -> tuple[str, ...]:
        if project == PROJECT:
            return ("zap_net", "lab_net", "egress_net", "host_net", "oast_net")
        return ("crapi_net", "publish_net")

    @staticmethod
    def _assert_empty(value: object) -> None:
        if value:
            raise ValueError("recurso do projeto ainda existe")
