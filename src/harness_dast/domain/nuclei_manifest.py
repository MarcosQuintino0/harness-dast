"""Validação estrutural dos metadados do catálogo Nuclei fixado no ADR 0122."""

import re
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)
from harness_dast.domain.secret_ref import ProfileModel

__all__ = ["NucleiManifest", "NucleiSeverity", "NucleiTemplateEntry"]

NucleiSeverity = Literal["critical", "high", "medium", "low", "info", "unknown"]

_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_HTTP_METHOD = re.compile(r"[!#$%&'*+.^_`|~0-9A-Z-]+")


def _validate_sha256(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("SHA-256 deve ter 64 dígitos hexadecimais")
    return value.lower()


def _validate_method(value: str) -> str:
    if not _HTTP_METHOD.fullmatch(value):
        raise ValueError("método HTTP deve ser um token em maiúsculas")
    return value


def _validate_path(value: str) -> str:
    if (
        value.startswith("~")
        or re.search(r'[\\:*?"<>|]', value)
        or not value.isprintable()
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("caminho deve ser relativo ao catálogo e usar segmentos POSIX")
    return value


_Sha256 = Annotated[str, AfterValidator(_validate_sha256)]
_Method = Annotated[str, AfterValidator(_validate_method)]
_Path = Annotated[str, AfterValidator(_validate_path)]
_Label = Annotated[str, StringConstraints(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")]


class NucleiTemplateEntry(ProfileModel):
    """Metadados imutáveis de um arquivo do catálogo, sem conteúdo das requisições.

    `methods` inclui os métodos já lidos pelo gerador, inclusive dos blocos `raw`.
    `category` é o subdiretório de `http/`, ou `None` para arquivos sem essa categoria.
    """

    # O Pydantic lê estes campos na serialização. Para o Vulture, F841 é um alias de V107.
    path: _Path
    sha256: _Sha256
    protocols: tuple[_Label, ...]  # noqa: F841, RUF100
    methods: tuple[_Method, ...]
    unsafe: StrictBool  # noqa: F841, RUF100
    raw: StrictBool
    code: StrictBool
    headless: StrictBool  # noqa: F841, RUF100
    oast: StrictBool
    dast: StrictBool  # noqa: F841, RUF100
    unparsed_method: StrictBool  # noqa: F841, RUF100
    tags: tuple[_Label, ...]
    severity: NucleiSeverity
    category: _Label | None

    @model_validator(mode="after")
    def validate_category(self) -> Self:
        """Confere a categoria declarada contra a posição do arquivo no catálogo."""
        path = self.path.split("/")
        expected = path[1] if len(path) >= 3 and path[0] == "http" else None
        if self.category != expected:
            raise ValueError("category deve coincidir com o primeiro diretório depois de http/")
        return self


class NucleiManifest(ProfileModel):
    """Metadados imutáveis do catálogo em uma única versão e com caminhos únicos.

    A validação compara os identificadores com os valores fixados no domínio. A conferência
    dos bytes do arquivo compactado e dos modelos cabe a quem fornece o manifesto.
    """

    schema_version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    nuclei_version: str
    templates_version: str
    templates_archive_sha256: _Sha256
    entries: tuple[NucleiTemplateEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        """Exige as versões e o SHA-256 fixados e recusa caminhos duplicados."""
        if self.nuclei_version != NUCLEI_VERSION:
            raise ValueError("nuclei_version deve coincidir com a versão fixada do Nuclei")
        if self.templates_version != TEMPLATES_VERSION:
            raise ValueError("templates_version deve coincidir com a versão fixada do catálogo")
        if self.templates_archive_sha256 != TEMPLATES_ARCHIVE_SHA256:
            raise ValueError("templates_archive_sha256 deve coincidir com o ZIP fixado do catálogo")
        if len({entry.path for entry in self.entries}) != len(self.entries):
            raise ValueError("o manifesto contém caminhos de modelos duplicados")
        return self
