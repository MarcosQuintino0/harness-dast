"""Falso em memória da porta `HostInspector`, com comportamento."""

from pathlib import Path

from harness_dast.domain.errors import ConfigError, ExternalToolError


class FakeHost:
    """Máquina simulada: Docker, imagens, portas, pastas e `uv` configuráveis.

    Atributos públicos configuram o cenário; `docker_calls` conta quantas vezes o Docker foi
    consultado (o `doctor` não deve consultá-lo à toa).
    """

    def __init__(self) -> None:
        self.docker_error: ExternalToolError | None = None
        self.docker_server = "27.3.1"
        self.images: tuple[str, ...] = (
            "zap:1@sha256:aaa",
            "socat:1@sha256:bbb",
            "hdast/scope-proxy:local",
        )
        self.compose_error: ConfigError | None = None
        self.present: set[str] = set(self.images)
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

    def compose_images(self, services: tuple[str, ...]) -> tuple[str, ...]:
        self.requested_services = services
        if self.compose_error is not None:
            raise self.compose_error
        return self.images

    def image_present(self, reference: str) -> bool:
        self.docker_calls += 1
        if self.docker_error is not None:
            raise self.docker_error
        return reference in self.present

    def port_is_free(self, port: int) -> bool:
        return port not in self.busy_ports

    def uv_version(self) -> str | None:
        return self.uv

    def directory_exists(self, path: Path) -> bool:
        return path in self.directories
