"""Modelo dos digests publicados junto com a versão da CLI."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_TAG_PATTERN = r"^[0-9][A-Za-z0-9_.-]{0,127}$"
_REPOSITORY_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_REPOSITORY_PATTERN = (
    rf"^(?:{_REPOSITORY_COMPONENT}(?::[0-9]+)?/)?"
    rf"(?:{_REPOSITORY_COMPONENT}/)*{_REPOSITORY_COMPONENT}$"
)
IMAGES_LOCK_RECOVERY = "Reinstale a CLI com o pacote publicado para a versão correta."


class LockedImage(BaseModel):
    """Identifica uma imagem publicada pelo repositório, pela tag e pelo digest do índice."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    repository: str = Field(max_length=255, pattern=_REPOSITORY_PATTERN)
    tag: str = Field(pattern=_TAG_PATTERN)
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    def reference(self) -> str:
        """Devolve a referência OCI com a tag e o digest fixado."""
        return f"{self.repository}:{self.tag}@{self.digest}"


class LockedImages(BaseModel):
    """Reúne as imagens próprias da pilha gerenciada.

    Attributes:
        zap: Imagem do ZAP.
        scope_proxy: Imagem do proxy de escopo (também usada pela cerca do Nuclei).
        nuclei: Imagem do Nuclei; só existe no esquema 2 (ADR 0122).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    zap: LockedImage
    scope_proxy: LockedImage
    nuclei: LockedImage | None = None


class ImagesLock(BaseModel):
    """Valida a versão do esquema e as imagens publicadas pela mesma tag da CLI.

    O esquema 1 (anterior ao ADR 0122) traz só o ZAP e o proxy: o Nuclei fica indisponível
    nessa instalação. O esquema 2 exige também a imagem do Nuclei.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: int = Field(ge=1, le=2)
    version: str = Field(pattern=_TAG_PATTERN)
    images: LockedImages

    @model_validator(mode="after")
    def check_tags(self) -> Self:
        """Exige que as tags de todas as imagens coincidam com a versão do pacote."""
        tags = {image.tag for image in self.images_present()}
        if tags != {self.version}:
            raise ValueError("As tags das imagens precisam coincidir com a versão do pacote.")
        return self

    @model_validator(mode="after")
    def check_nuclei_for_schema(self) -> Self:
        """Exige o Nuclei no esquema 2 e recusa o Nuclei no esquema 1."""
        if (self.schema_version == 2) != (self.images.nuclei is not None):
            raise ValueError("A imagem do Nuclei existe só no esquema 2 e é obrigatória nele.")
        return self

    def images_present(self) -> tuple[LockedImage, ...]:
        """Imagens declaradas no arquivo, na ordem zap, proxy e Nuclei."""
        images = self.images
        listed = (images.zap, images.scope_proxy, images.nuclei)
        return tuple(image for image in listed if image is not None)

    @property
    def supports_nuclei(self) -> bool:
        """Se a instalação publicou a imagem do Nuclei (esquema 2)."""
        return self.images.nuclei is not None
