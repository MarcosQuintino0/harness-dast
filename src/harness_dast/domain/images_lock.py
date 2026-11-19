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
    """Reúne as duas imagens próprias exigidas pela pilha gerenciada."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    zap: LockedImage
    scope_proxy: LockedImage


class ImagesLock(BaseModel):
    """Valida a versão do esquema e as imagens publicadas pela mesma tag da CLI."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: int = Field(ge=1, le=1)
    version: str = Field(pattern=_TAG_PATTERN)
    images: LockedImages

    @model_validator(mode="after")
    def check_tags(self) -> Self:
        """Exige que as tags das duas imagens coincidam com a versão do pacote."""
        if self.images.zap.tag != self.version or self.images.scope_proxy.tag != self.version:
            raise ValueError("As tags das imagens precisam coincidir com a versão do pacote.")
        return self
