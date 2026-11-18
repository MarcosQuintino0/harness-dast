"""Seleção, download e compatibilidade das imagens próprias da pilha."""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from harness_dast.domain.errors import ConfigError, ExternalToolError

PROXY_SERVICE = "scope-proxy"
OWN_SERVICES = ("zap", PROXY_SERVICE)
_ENV_BY_SERVICE = (("zap", "HDAST_ZAP_IMAGE"), (PROXY_SERVICE, "HDAST_SCOPE_PROXY_IMAGE"))
IMAGE_RECOVERY = "Rode hdast stack pull ou use HDAST_STACK_BUILD=1 para construir localmente."


class ImageInfo(BaseModel):
    """Metadados públicos de uma imagem já presente no Docker local."""

    model_config = ConfigDict(frozen=True)

    version: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9.+!_-]+$")


class ImageStore(Protocol):
    """Referências do Compose e operações sobre imagens, sem subir contêineres."""

    def compose_images(
        self, services: tuple[str, ...], overrides: Mapping[str, str]
    ) -> dict[str, str]:
        """Resolve referências por serviço ou levanta `ConfigError` para Compose inválido."""
        ...

    def inspect_image(self, reference: str) -> ImageInfo | None:
        """Lê a imagem local ou devolve `None` se ausente; falhas levantam `ExternalToolError`."""
        ...

    def pull_image(self, reference: str) -> None:
        """Baixa a referência ou levanta `ExternalToolError` se o Docker falhar."""
        ...


class StackImages:
    """Usa a mesma seleção e checagem de versão na subida e no diagnóstico."""

    def __init__(self, store: ImageStore, cli_version: str) -> None:
        """Recebe o Docker e a versão do pacote instalado que executa a CLI."""
        self._store = store
        self._cli_version = cli_version

    def references(self, services: tuple[str, ...], *, local: bool) -> dict[str, str]:
        """Resolve as imagens por serviço e exige as duas referências próprias."""
        overrides = (
            {env: f"hdast/{service}:local" for service, env in _ENV_BY_SERVICE} if local else {}
        )
        images = self._store.compose_images(services, overrides)
        if any(service not in images for service in OWN_SERVICES):
            raise ConfigError(
                "Falta declarar a imagem do ZAP ou a do proxy de escopo no compose.yaml.",
                hint="Restaure o compose.yaml original.",
            )
        return images

    def inspect(self, references: Mapping[str, str]) -> dict[str, ImageInfo | None]:
        """Inspeciona uma vez cada referência, mesmo quando vários serviços a usam."""
        return {
            image: self._store.inspect_image(image) for image in dict.fromkeys(references.values())
        }

    def require_proxy_version(self, proxy: ImageInfo) -> str:
        """Devolve a versão do proxy ou levanta `ExternalToolError` se faltar ou divergir."""
        if proxy.version == self._cli_version:
            return self._cli_version
        found = f"tem versão {proxy.version}" if proxy.version else "está sem rótulo de versão"
        raise ExternalToolError(
            f"A imagem do proxy de escopo {found}. A CLI exige a versão {self._cli_version}.",
            hint=IMAGE_RECOVERY,
        )

    def require_ready(self, references: Mapping[str, str]) -> None:
        """Exige as imagens próprias locais e a versão compatível do proxy."""
        inspected = self.inspect(references)
        missing = [ref for ref, image in inspected.items() if image is None]
        if missing:
            raise ExternalToolError(
                f"Imagens da pilha ausentes: {', '.join(missing)}.", hint=IMAGE_RECOVERY
            )
        proxy = inspected[references[PROXY_SERVICE]]
        if proxy is not None:
            self.require_proxy_version(proxy)

    def compose_env(self, references: Mapping[str, str]) -> dict[str, str]:
        """Fixa no processo filho as referências consultadas e a versão esperada no build."""
        images = {env: references[service] for service, env in _ENV_BY_SERVICE}
        return {**images, "HDAST_IMAGE_VERSION": self._cli_version}

    def pull(self) -> tuple[str, ...]:
        """Baixa as duas imagens próprias configuradas e devolve suas referências."""
        references = self.references(OWN_SERVICES, local=False)
        for reference in references.values():
            self._store.pull_image(reference)
        return tuple(references.values())


def use_local_build(environ: Mapping[str, str]) -> bool:
    """Habilita o build local quando `HDAST_STACK_BUILD` vale literalmente `1`."""
    return environ.get("HDAST_STACK_BUILD") == "1"
