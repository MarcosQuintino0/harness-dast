"""Falso em memória da porta `HostInspector`, com comportamento."""

from collections.abc import Mapping
from pathlib import Path

from harness_dast import __version__
from harness_dast.application.stack_images import ImageInfo, StackImages
from harness_dast.domain.errors import ConfigError, ExternalToolError
from harness_dast.domain.images_lock import ImagesLock, LockedImage, LockedImages


def published_images(version: str = __version__, *, nuclei: bool = False) -> ImagesLock:
    """Imagens publicadas simuladas com digests distintos.

    Sem `nuclei` é o esquema 1 (anterior ao Nuclei); com `nuclei` é o esquema 2.
    """
    return ImagesLock(
        schema_version=2 if nuclei else 1,
        version=version,
        images=LockedImages(
            zap=LockedImage(
                repository="registry.example/zap", tag=version, digest="sha256:" + "a" * 64
            ),
            scope_proxy=LockedImage(
                repository="registry.example/proxy", tag=version, digest="sha256:" + "b" * 64
            ),
            nuclei=(
                LockedImage(
                    repository="registry.example/nuclei", tag=version, digest="sha256:" + "c" * 64
                )
                if nuclei
                else None
            ),
        ),
    )


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
            "scope-proxy-nuclei": "registry.example/scope-proxy:1",
            "nuclei": "registry.example/nuclei:1",
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
        self.images_lock: ImagesLock | None = None
        self.build_contexts = True

    def stack_images(self) -> StackImages:
        """Monta a seleção com os digests e os contextos simulados."""
        return StackImages(
            self,
            __version__,
            load_lock=lambda: self.images_lock,
            has_build_contexts=lambda: self.build_contexts,
        )

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
            images["scope-proxy-nuclei"] = overrides["HDAST_SCOPE_PROXY_IMAGE"]
            if "HDAST_NUCLEI_IMAGE" in overrides:
                images["nuclei"] = overrides["HDAST_NUCLEI_IMAGE"]
        return {service: images[service] for service in services if service in images}

    def inspect_image(self, reference: str) -> ImageInfo | None:
        self.docker_calls += 1
        if self.docker_error is not None:
            raise self.docker_error
        return (
            ImageInfo(version=self.versions.get(reference)) if reference in self.present else None
        )

    def pull_image(self, reference: str) -> None:
        self.docker_calls += 1
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
