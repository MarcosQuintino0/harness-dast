"""Conta metadados de um catálogo Nuclei local, sem extrair arquivos ou executar modelos."""

import argparse
import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from harness_dast.adapters.storage.profile_repository import read_profile_text
from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml, parse_yaml_document
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope import OutboundRequest, ScopeGuard

_ROOT = Path(__file__).resolve().parents[1]
_LAB_PROFILES = tuple(
    _ROOT / "lab" / name / "product-profile" / "target.yml" for name in ("pilot", "crapi", "vampi")
)
_MAX_YAML_BYTES = 256 * 1024
_PROTOCOLS = frozenset(
    {
        "http",
        "requests",
        "dns",
        "file",
        "headless",
        "network",
        "tcp",
        "ssl",
        "websocket",
        "whois",
        "code",
        "javascript",
        "workflows",
    }
)
_VETO_TAGS = frozenset({"dos", "intrusive", "bruteforce", "fuzz", "default-logins"})
_FUZZ_KEYS = frozenset({"dast", "fuzz", "fuzzing", "fuzzing-rules"})
_REQUEST_EXTRA_KEYS = frozenset({"matchers", "matchers-condition"})
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_LITERAL_PATH = re.compile(r"/[a-zA-Z0-9._~/\-]*")
_LARGE_EXPOSURE = re.compile(
    r"heapdump|threaddump|backup|download|\.zip$|\.tar(?:\.gz)?$|\.sql$|\.rar$|\.7z$",
    re.IGNORECASE,
)


class RequestBlock(BaseModel):
    """Campos usados para contabilizar um bloco HTTP."""

    model_config = ConfigDict(frozen=True, strict=True, extra="allow")
    method: str = "GET"
    path: list[str] = Field(default_factory=list)


class RequestBlocks(RootModel[list[RequestBlock]]):
    """Sequência de blocos HTTP no catálogo."""

    model_config = ConfigDict(frozen=True, strict=True)


class TemplateInfo(BaseModel):
    """Metadados declarados pelo catálogo."""

    model_config = ConfigDict(frozen=True, strict=True, extra="ignore")
    tags: str | list[str] = ""


class Metadata(BaseModel):
    """Metadados de auditoria de um arquivo, sem URLs ou conteúdo dos pedidos."""

    model_config = ConfigDict(frozen=True)
    file: str
    sha256: str
    protocols: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    path_count: int = 0
    unsafe: bool = False
    raw: bool = False
    code: bool = False
    headless: bool = False
    oast: bool = False
    dast: bool = False
    unreadable: bool = False

    def vetoes(self) -> tuple[str, ...]:
        """Informa os vetos estruturais, com possibilidade de sobreposição."""
        flags = ("unsafe", "raw", "code", "headless", "oast", "dast", "unreadable")
        reasons = [flag for flag in flags if getattr(self, flag)]
        if self.protocols not in (("http",), ("requests",)):
            reasons.append("not_http_only")
        reasons.extend(f"tag:{tag}" for tag in sorted(_VETO_TAGS.intersection(self.tags)))
        return tuple(reasons)


class Census(BaseModel):
    """Registra os totais e os metadados das entradas identificadas como modelos."""

    model_config = ConfigDict(frozen=True)
    archive_sha256: str
    yaml_files: int
    templates: int
    unreadable_yaml_files: int
    after_vetoes: int
    statically_projectable: int
    whole_profile_matches: dict[str, int]
    distinct_literal_get_exposure_paths: int
    veto_counts: dict[str, int]
    models: list[Metadata]


def _parse_catalog_entry(path: str, raw: bytes) -> tuple[Metadata, list[tuple[str, str]]] | None:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = parse_yaml_document(raw.decode("utf-8-sig"), "modelo do catálogo")
    except (ConfigError, UnicodeDecodeError) as error:
        raise ConfigError("Não foi possível interpretar um YAML do catálogo.") from error
    if "id" not in document or "info" not in document:
        return None
    protocols = tuple(sorted(_PROTOCOLS.intersection(document)))
    blocks = document.get("http", document.get("requests", []))
    try:
        info = TemplateInfo.model_validate(document["info"])
        requests = RequestBlocks.model_validate(blocks).root
    except ValidationError:
        return Metadata(file=path, sha256=digest, protocols=protocols, unreadable=True), []
    tag_values = info.tags.split(",") if isinstance(info.tags, str) else info.tags
    fields = set(document)
    for request in requests:
        fields.update(request.model_extra or {})
    metadata = Metadata(
        file=path,
        sha256=digest,
        protocols=protocols,
        methods=tuple(sorted({request.method for request in requests})),
        path_count=sum(len(request.path) for request in requests),
        tags=tuple(sorted({tag.strip().lower() for tag in tag_values if tag.strip()})),
        unsafe="unsafe" in fields,
        raw="raw" in fields,
        code="code" in fields,
        headless="headless" in fields,
        oast=b"interactsh" in raw.lower(),
        dast=bool(_FUZZ_KEYS.intersection(fields)) or _is_dast_path(path, tag_values),
    )
    if metadata.vetoes() or document.keys() - {"id", "info", *metadata.protocols}:
        return metadata, []
    return metadata, _project_requests(requests)


def _is_dast_path(path: str, tags: list[str]) -> bool:
    return bool(
        _FUZZ_KEYS.intersection(PurePosixPath(path).parts[:-1])
        or _FUZZ_KEYS.intersection(tag.strip().lower() for tag in tags)
    )


def _project_requests(requests: list[RequestBlock]) -> list[tuple[str, str]]:
    projected: list[tuple[str, str]] = []
    for request in requests:
        extra = request.model_extra or {}
        if (
            request.method not in _READ_METHODS
            or extra.keys() - _REQUEST_EXTRA_KEYS
            or not request.path
        ):
            return []
        for expression in request.path:
            suffix = expression.removeprefix("{{BaseURL}}")
            if suffix == expression or not _LITERAL_PATH.fullmatch(suffix):
                return []
            projected.append((request.method, suffix))
    return projected


def _load_profile(path: Path) -> ProductProfile:
    return ProductProfile.from_data(parse_profile_yaml(read_profile_text(path)))


def _match_profiles(
    requests: list[tuple[str, str]],
    profiles: tuple[tuple[str, str, ScopeGuard], ...],
    matches: Counter[str],
) -> None:
    for name, base_url, guard in profiles:
        allowed = all(
            guard.evaluate(OutboundRequest(method=method, url=base_url + path)).verdict == "allowed"
            for method, path in requests
        )
        matches[name] += int(allowed)


def _zip_yaml_entries(archive: ZipFile) -> list[ZipInfo]:
    return sorted(
        (
            entry
            for entry in archive.infolist()
            if entry.filename.lower().endswith((".yaml", ".yml"))
        ),
        key=lambda entry: entry.filename,
    )


def census(archive_path: Path, expected_sha256: str, profiles: Sequence[ProductProfile]) -> Census:
    """Compara a projeção literal completa com os perfis, sem tocar em alvos ou aprovações."""
    profile_guards = tuple(
        (profile.product, profile.environment.base_url.rstrip("/"), ScopeGuard(profile.scope))
        for profile in profiles
    )
    matches: Counter[str] = Counter({profile.product: 0 for profile in profiles})
    vetoes: Counter[str] = Counter()
    exposures: set[str] = set()
    manifest: list[Metadata] = []
    unreadable_yaml = projectable = after_vetoes = 0
    with archive_path.open("rb") as source:
        archive_digest = hashlib.file_digest(source, "sha256").hexdigest()
        if archive_digest != expected_sha256:
            raise ConfigError("O SHA-256 do catálogo difere do esperado. Confira o arquivo ZIP.")
        source.seek(0)
        with ZipFile(source) as archive:
            entries = _zip_yaml_entries(archive)
            for entry in entries:
                path = entry.filename.partition("/")[2]
                parsed = _read_catalog_entry(archive, entry, path)
                if parsed is None:
                    unreadable_yaml += 1
                    continue
                if not parsed:
                    continue
                metadata, requests = parsed
                manifest.append(metadata)
                reasons = metadata.vetoes()
                vetoes.update(reasons)
                after_vetoes += int(not reasons)
                if requests:
                    projectable += 1
                    _match_profiles(requests, profile_guards, matches)
                    exposures.update(_exposure_paths(path, requests))
    return Census(
        archive_sha256=archive_digest,
        yaml_files=len(entries),
        templates=len(manifest),
        unreadable_yaml_files=unreadable_yaml,
        after_vetoes=after_vetoes,
        statically_projectable=projectable,
        whole_profile_matches=dict(matches),
        distinct_literal_get_exposure_paths=len(exposures),
        veto_counts=dict(sorted(vetoes.items())),
        models=manifest,
    )


def _read_catalog_entry(
    archive: ZipFile, entry: ZipInfo, path: str
) -> tuple[Metadata, list[tuple[str, str]]] | tuple[()] | None:
    if not path or entry.file_size > _MAX_YAML_BYTES:
        return None
    try:
        return _parse_catalog_entry(path, archive.read(entry)) or ()
    except ConfigError:
        return None


def _exposure_paths(path: str, requests: list[tuple[str, str]]) -> set[str]:
    if not path.startswith("http/exposures/") or any(method != "GET" for method, _ in requests):
        return set()
    return {suffix for _, suffix in requests if not _LARGE_EXPOSURE.search(suffix)}


def main(argv: Sequence[str] | None = None) -> None:
    """Grava o censo em um arquivo JSON novo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="ZIP local do catálogo.")
    parser.add_argument("sha256", help="SHA-256 esperado do ZIP.")
    parser.add_argument("output", type=Path, help="Arquivo JSON a criar.")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.sha256):
        parser.error("Informe o SHA-256 esperado como 64 dígitos hexadecimais minúsculos.")
    try:
        report = census(args.archive, args.sha256, tuple(map(_load_profile, _LAB_PROFILES)))
        with args.output.open("x", encoding="utf-8") as output:
            output.write(report.model_dump_json(indent=2) + "\n")
    except ConfigError as error:
        parser.error(error.message)
    except (OSError, BadZipFile):
        parser.error("Confira o arquivo ZIP e informe um destino novo com permissão de escrita.")


if __name__ == "__main__":
    main()
