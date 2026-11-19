"""Seleção, download e compatibilidade das imagens próprias da pilha."""

from collections.abc import Callable, Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from harness_dast.domain.errors import ConfigError, ExternalToolError, StackBuildForbidden
from harness_dast.domain.images_lock import IMAGES_LOCK_RECOVERY, ImagesLock

PROXY_SERVICE = "scope-proxy"
NUCLEI_SERVICE = "nuclei"
OWN_SERVICES = ("zap", PROXY_SERVICE)
_ENV_BY_SERVICE = (("zap", "HDAST_ZAP_IMAGE"), (PROXY_SERVICE, "HDAST_SCOPE_PROXY_IMAGE"))
NUCLEI_IMAGE_ENV = "HDAST_NUCLEI_IMAGE"
NUCLEI_UNAVAILABLE = (
    "Esta instalação foi publicada sem a imagem do Nuclei (images.lock.json versão 1), "
    "então o Nuclei está indisponível."
)
NUCLEI_RECOVERY = (
    "Reinstale a CLI com uma versão que inclua o Nuclei ou desligue extra_checks.nuclei."
)
IMAGE_RECOVERY = "Rode hdast stack pull. Em um clone de desenvolvimento, pode usar --build."


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

    def __init__(
        self,
        store: ImageStore,
        cli_version: str,
        *,
        load_lock: Callable[[], ImagesLock | None],
        has_build_contexts: Callable[[], bool],
    ) -> None:
        """Recebe o Docker, a versão da CLI e as consultas aos arquivos da instalação."""
        self._store = store
        self._cli_version = cli_version
        self._load_lock = load_lock
        self._has_build_contexts = has_build_contexts

    def references(self, services: tuple[str, ...], *, local: bool) -> dict[str, str]:
        """Resolve as referências e recusa build local fora de um clone antes do Docker."""
        lock = self._load_lock()
        # Com a trava do esquema 1 o Nuclei não existe: sai da lista em vez de cair no padrão
        # do compose, que apontaria para uma imagem que esta instalação nunca publicou.
        wanted = (
            services
            if lock is None or lock.supports_nuclei
            else tuple(service for service in services if service != NUCLEI_SERVICE)
        )
        images = self._store.compose_images(wanted, self._overrides(lock, local=local))
        required = tuple(s for s in (*OWN_SERVICES, NUCLEI_SERVICE) if s in wanted)
        if any(service not in images for service in required):
            raise ConfigError(
                "Falta declarar a imagem do ZAP, a do proxy de escopo ou a do Nuclei "
                "no compose.yaml.",
                hint="Restaure o compose.yaml original.",
            )
        return images

    def nuclei_available(self) -> bool:
        """Diz se esta instalação traz a imagem do Nuclei.

        Sem `images.lock.json` (clone) vale `True`; com o esquema 1, `False`.

        Raises:
            ConfigError: Arquivo de digests inválido.
        """
        lock = self._load_lock()
        return lock is None or lock.supports_nuclei

    def require_nuclei(self) -> None:
        """Levanta `ConfigError` com orientação se o Nuclei estiver indisponível."""
        if not self.nuclei_available():
            raise ConfigError(NUCLEI_UNAVAILABLE, hint=NUCLEI_RECOVERY)

    def _overrides(self, lock: ImagesLock | None, *, local: bool) -> dict[str, str]:
        if lock is not None and lock.version != self._cli_version:
            raise ConfigError(
                f"O arquivo images.lock.json é da versão {lock.version}, "
                f"mas a CLI é da versão {self._cli_version}.",
                hint=IMAGES_LOCK_RECOVERY,
            )
        if local:
            if lock is not None or not self._has_build_contexts():
                raise StackBuildForbidden(
                    f"Esta instalação usa as imagens publicadas da versão {self._cli_version}. "
                    "Construir a cerca só é possível num clone de desenvolvimento.",
                    hint="Retire --build e HDAST_STACK_BUILD=1. Use hdast stack pull.",
                )
            local_images = {env: f"hdast/{service}:local" for service, env in _ENV_BY_SERVICE}
            return {**local_images, NUCLEI_IMAGE_ENV: f"hdast/{NUCLEI_SERVICE}:local"}
        if lock is None:
            return {}
        overrides = {
            "HDAST_ZAP_IMAGE": lock.images.zap.reference(),
            "HDAST_SCOPE_PROXY_IMAGE": lock.images.scope_proxy.reference(),
        }
        if lock.images.nuclei is not None:
            overrides[NUCLEI_IMAGE_ENV] = lock.images.nuclei.reference()
        return overrides

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
        if NUCLEI_SERVICE in references:
            images[NUCLEI_IMAGE_ENV] = references[NUCLEI_SERVICE]
        return {**images, "HDAST_IMAGE_VERSION": self._cli_version}

    def pull(self) -> tuple[str, ...]:
        """Baixa as imagens próprias configuradas (com o Nuclei, se a instalação o traz).

        Devolve as referências baixadas.
        """
        services = (*OWN_SERVICES, NUCLEI_SERVICE) if self.nuclei_available() else OWN_SERVICES
        references = self.references(services, local=False)
        for reference in references.values():
            self._store.pull_image(reference)
        return tuple(references.values())


def use_local_build(environ: Mapping[str, str]) -> bool:
    """Habilita o build local quando `HDAST_STACK_BUILD` vale literalmente `1`."""
    return environ.get("HDAST_STACK_BUILD") == "1"
