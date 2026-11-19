"""Validação estrutural dos metadados do catálogo Nuclei fixado no ADR 0122."""

import re
from enum import StrEnum
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

__all__ = [
    "NucleiExclusion",
    "NucleiManifest",
    "NucleiPermissions",
    "NucleiSelection",
    "NucleiSeverity",
    "NucleiTemplateEntry",
    "NucleiVeto",
    "select_templates",
    "veto_reasons",
]

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
    protocols: tuple[_Label, ...]
    methods: tuple[_Method, ...]
    unsafe: StrictBool
    raw: StrictBool
    code: StrictBool
    headless: StrictBool
    oast: StrictBool
    dast: StrictBool
    unparsed_method: StrictBool
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


class NucleiVeto(StrEnum):
    """Motivos de veto permanente de um modelo (ADR 0122); nenhuma permissão os levanta."""

    NON_HTTP = "non_http"
    UNSAFE = "unsafe"
    CODE = "code"
    HEADLESS = "headless"
    OAST = "oast"
    DAST = "dast"
    UNPARSED_METHOD = "unparsed_method"
    TAG_DOS = "tag_dos"
    TAG_INTRUSIVE = "tag_intrusive"
    TAG_BRUTEFORCE = "tag_bruteforce"
    TAG_FUZZ = "tag_fuzz"
    TAG_DEFAULT_LOGINS = "tag_default_logins"


class NucleiExclusion(StrEnum):
    """Motivos de exclusão que dependem das permissões da execução."""

    WRITES_NOT_ALLOWED = "writes_not_allowed"
    DELETE_NOT_ALLOWED = "delete_not_allowed"
    LOGIN_READ_ONLY = "login_read_only"


_VETOED_TAGS: dict[str, NucleiVeto] = {
    "dos": NucleiVeto.TAG_DOS,
    "intrusive": NucleiVeto.TAG_INTRUSIVE,
    "bruteforce": NucleiVeto.TAG_BRUTEFORCE,
    "fuzz": NucleiVeto.TAG_FUZZ,
    "default-logins": NucleiVeto.TAG_DEFAULT_LOGINS,
}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DELETE_METHOD = "DELETE"


def veto_reasons(entry: NucleiTemplateEntry) -> frozenset[NucleiVeto]:
    """Lista os vetos permanentes de um modelo; vazio significa "pode ser considerado".

    Falha fechado: protocolo que não seja só `http` (inclusive lista vazia) e método que o
    gerador do manifesto não conseguiu ler (`unparsed_method`) vetam. `raw` sozinho não veta.

    Args:
        entry: Metadados do modelo.

    Returns:
        Conjunto imutável de vetos.
    """
    reasons: set[NucleiVeto] = set()
    if set(entry.protocols) != {"http"}:
        reasons.add(NucleiVeto.NON_HTTP)
    flags = (
        (entry.unsafe, NucleiVeto.UNSAFE),
        (entry.code, NucleiVeto.CODE),
        (entry.headless, NucleiVeto.HEADLESS),
        (entry.oast, NucleiVeto.OAST),
        (entry.dast, NucleiVeto.DAST),
        (entry.unparsed_method, NucleiVeto.UNPARSED_METHOD),
    )
    reasons.update(veto for active, veto in flags if active)
    reasons.update(_VETOED_TAGS[tag] for tag in entry.tags if tag in _VETOED_TAGS)
    return frozenset(reasons)


class NucleiPermissions(ProfileModel):
    """O que o pedido autoriza além da leitura.

    Attributes:
        writes: `POST`, `PUT` e `PATCH` permitidos (permissão de escrita de dados).
        delete: `DELETE` permitido (só a pedido explícito da pessoa).
        login: A execução usa conta autenticada; então só modelos de leitura rodam.
    """

    writes: StrictBool = False
    delete: StrictBool = False
    login: StrictBool = False


class NucleiSelection(ProfileModel):
    """Resultado determinístico da escolha dos modelos.

    Attributes:
        paths: Caminhos escolhidos, em ordem alfabética.
        excluded: Pares (motivo, contagem) em ordem alfabética do motivo. Um modelo com mais
            de um motivo conta em cada um, então a soma pode passar do total excluído.
    """

    paths: tuple[str, ...]
    excluded: tuple[tuple[str, int], ...]


def _method_exclusions(
    methods: tuple[str, ...], permissions: NucleiPermissions
) -> frozenset[NucleiExclusion]:
    declared = frozenset(methods) or frozenset({"GET"})
    deletes = _DELETE_METHOD in declared
    # Método fora das listas conhecidas conta como escrita (falha fechado).
    writes = bool(declared - _READ_METHODS - {_DELETE_METHOD})
    reasons: set[NucleiExclusion] = set()
    if writes and not permissions.writes:
        reasons.add(NucleiExclusion.WRITES_NOT_ALLOWED)
    if deletes and not permissions.delete:
        reasons.add(NucleiExclusion.DELETE_NOT_ALLOWED)
    if (writes or deletes) and permissions.login:
        reasons.add(NucleiExclusion.LOGIN_READ_ONLY)
    return frozenset(reasons)


def select_templates(manifest: NucleiManifest, permissions: NucleiPermissions) -> NucleiSelection:
    """Escolhe os modelos que podem rodar: sem veto e com métodos dentro das permissões.

    Sem `methods` declarados vale `GET` (padrão do Nuclei). Método desconhecido conta como
    escrita. Com `login`, só entram modelos de leitura.

    Args:
        manifest: Manifesto validado do catálogo fixado.
        permissions: Permissões da execução.

    Returns:
        Os caminhos escolhidos e a contagem por motivo de exclusão, ordenados.
    """
    chosen: list[str] = []
    counts: dict[str, int] = {}
    for entry in manifest.entries:
        reasons = [str(v) for v in veto_reasons(entry)]
        reasons += [str(e) for e in _method_exclusions(entry.methods, permissions)]
        if not reasons:
            chosen.append(entry.path)
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return NucleiSelection(paths=tuple(sorted(chosen)), excluded=tuple(sorted(counts.items())))
