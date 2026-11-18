"""Falso em memória da porta `HostInspector`, com comportamento."""

from collections.abc import Mapping
from pathlib import Path

from harness_dast import __version__
from harness_dast.application.stack_images import ImageInfo
from harness_dast.domain.errors import ConfigError, ExternalToolError


class FakeHost:
    """Máquina simulada: Docker, imagens, portas, pastas e `uv` configuráveis.

    Atributos públicos configuram o cenário; `docker_calls` conta quantas vezes o Docker foi
    consultado (o `doctor` não deve consultá-lo à toa).
    """

    def __init__(self) -> None:
        self.docker_error: ExternalToolError | None = None
        self.docker_server = "27.3.1"
        self.images = {
            "zap": "zap:1@sha256:aaa",
            "zap-gateway": "socat:1@sha256:bbb",
            "scope-proxy": "registry.example/scope-proxy:1",
            "proxy-gateway": "socat:1@sha256:bbb",
        }
        self.compose_error: ConfigError | None = None
        self.remote = set(self.images.values())
        self.present = set(self.remote)
        self.versions: dict[str, str | None] = {self.images["scope-proxy"]: __version__}
        self.busy_ports: set[int] = set()
        self.uv: str | None = "0.5.1"
        self.directories: set[Path] = set()
        self.docker_calls = 0
        self.requested_services: tuple[str, ...] = ()

    def docker_version(self) -> str:
        self.docker_calls += 1
        if self.docker_error is not None:
            raise self.docker_error
        return self.docker_server

    def compose_images(
        self, services: tuple[str, ...], overrides: Mapping[str, str]
    ) -> dict[str, str]:
        self.requested_services = services
        if self.compose_error is not None:
            raise self.compose_error
        images = dict(self.images)
        if overrides:
            images.update(zap=overrides["HDAST_ZAP_IMAGE"])
            images["scope-proxy"] = overrides["HDAST_SCOPE_PROXY_IMAGE"]
        return {service: images[service] for service in services if service in images}

    def inspect_image(self, reference: str) -> ImageInfo | None:
        self.docker_calls += 1
        if self.docker_error is not None:
            raise self.docker_error
        return (
            ImageInfo(version=self.versions.get(reference)) if reference in self.present else None
        )

    def pull_image(self, reference: str) -> None:
        if self.docker_error is not None:
            raise self.docker_error
        if reference not in self.remote:
            raise ExternalToolError("Imagem ausente no registro.", hint="Confira a publicação.")
        self.present.add(reference)

    def port_is_free(self, port: int) -> bool:
        return port not in self.busy_ports

    def uv_version(self) -> str | None:
        return self.uv

    def directory_exists(self, path: Path) -> bool:
        return path in self.directories
