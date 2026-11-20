"""Gera o manifesto do catálogo nuclei-templates a partir do ZIP oficial, sem rede.

Lê o ZIP SEM extrair e sem executar nada de dentro dele: só interpreta o YAML de cada modelo
com o leitor estrito do projeto e grava os metadados no formato `NucleiManifest` (ADR 0122).
Recusa o ZIP se o SHA-256 diferir do esperado. O resultado é reproduzível: entradas em ordem
alfabética e gzip sem data.
"""

import argparse
import gzip
import hashlib
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from pydantic import ValidationError

from harness_dast.adapters.storage.strict_yaml import parse_yaml_document
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_manifest import (
    NucleiManifest,
    NucleiSeverity,
    NucleiTemplateEntry,
)
from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)

_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "src/harness_dast/adapters/nuclei/data/nuclei-manifest.json.gz"
)
_MAX_YAML_BYTES = 256 * 1024
_PROTOCOLS = frozenset(
    {
        "http",
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
_FUZZ_KEYS = frozenset({"dast", "fuzz", "fuzzing", "fuzzing-rules"})
_SEVERITIES: dict[str, NucleiSeverity] = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
}
_METHOD = re.compile(r"[!#$%&'*+.^_`|~0-9A-Z-]+")
_LABEL = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_GZIP_LEVEL = 9


def _request_blocks(document: Mapping[str, Any]) -> list[Any]:
    # `requests` é o nome antigo do bloco `http`; o catálogo mistura os dois.
    blocks: list[Any] = []
    for key in ("http", "requests"):
        value = document.get(key)
        if isinstance(value, list):
            blocks.extend(value)
    return blocks


def _raw_method(raw: object) -> str | None:
    """Método da primeira linha de um pedido `raw`; `None` se ilegível."""
    if not isinstance(raw, str):
        return None
    first = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    token = first.split(" ", 1)[0]
    return token if _METHOD.fullmatch(token) else None


def _block_methods(block: Mapping[str, Any]) -> tuple[set[str], bool]:
    """Métodos de um bloco e se algum não pôde ser lido."""
    methods: set[str] = set()
    unparsed = False
    raws = block.get("raw")
    if raws is not None:
        for raw in raws if isinstance(raws, list) else [raws]:
            method = _raw_method(raw)
            if method is None:
                unparsed = True
            else:
                methods.add(method)
    if "method" in block or raws is None:
        method = block.get("method", "GET")
        if isinstance(method, str) and _METHOD.fullmatch(method):
            methods.add(method)
        else:
            unparsed = True
    return methods, unparsed


def _tags(info: Mapping[str, Any]) -> tuple[str, ...]:
    value = info.get("tags", "")
    if isinstance(value, str):
        items: list[Any] = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        return ()
    cleaned = {str(item).strip().lower() for item in items}
    # Rótulo fora do padrão é descartado: nenhuma etiqueta de veto tem esse formato.
    return tuple(sorted(tag for tag in cleaned if _LABEL.fullmatch(tag)))


def _is_dast(path: str, tags: tuple[str, ...], document: Mapping[str, Any], keys: set[str]) -> bool:
    return bool(
        _FUZZ_KEYS.intersection(document)
        or _FUZZ_KEYS.intersection(keys)
        or _FUZZ_KEYS.intersection(PurePosixPath(path).parts[:-1])
        or _FUZZ_KEYS.intersection(tags)
    )


def _category(path: str) -> str | None:
    parts = path.split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "http" else None


def parse_template(path: str, raw: bytes) -> NucleiTemplateEntry | None:
    """Converte um arquivo YAML do catálogo em entrada do manifesto.

    Devolve `None` para arquivo que não é modelo (sem `id` e `info`, como os de apoio).

    Raises:
        ConfigError: YAML que o leitor estrito recusa ou texto que não é UTF-8.
        ValidationError: Metadado que o modelo do manifesto recusa (por exemplo, caminho).
    """
    try:
        document = parse_yaml_document(raw.decode("utf-8-sig"), "modelo do catálogo")
    except UnicodeDecodeError:
        raise ConfigError("Modelo do catálogo não é UTF-8.") from None
    info = document.get("info")
    if "id" not in document or not isinstance(info, dict):
        return None
    blocks = [block for block in _request_blocks(document) if isinstance(block, dict)]
    methods: set[str] = set()
    unparsed = False
    block_keys: set[str] = set()
    for block in blocks:
        found, bad = _block_methods(block)
        methods |= found
        unparsed = unparsed or bad
        block_keys.update(str(key) for key in block)
    tags = _tags(info)
    protocols = _PROTOCOLS.intersection(document)
    if _request_blocks(document):
        protocols = protocols | {"http"}
    severity = str(info.get("severity", "")).strip().lower()
    return NucleiTemplateEntry(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        protocols=tuple(sorted(protocols)),
        methods=tuple(sorted(methods)),
        unsafe="unsafe" in block_keys or "unsafe" in document,
        raw="raw" in block_keys,
        code="code" in document,
        headless="headless" in document,
        oast=b"interactsh" in raw.lower(),
        dast=_is_dast(path, tags, document, block_keys),
        unparsed_method=unparsed,
        tags=tags,
        severity=_SEVERITIES.get(severity, "unknown"),
        category=_category(path),
    )


def _yaml_entries(archive: ZipFile) -> list[ZipInfo]:
    return sorted(
        (
            entry
            for entry in archive.infolist()
            if not entry.is_dir() and entry.filename.lower().endswith((".yaml", ".yml"))
        ),
        key=lambda entry: entry.filename,
    )


def build_manifest(archive_path: Path, expected_sha256: str) -> tuple[NucleiManifest, Counter[str]]:
    """Lê o ZIP conferido e monta o manifesto, com a contagem do que não entrou.

    Args:
        archive_path: ZIP oficial da tag do catálogo.
        expected_sha256: SHA-256 esperado do ZIP.

    Returns:
        O manifesto validado e as contagens de arquivos pulados (`not_template`, `unreadable`,
        `invalid_metadata`, `oversized`). Arquivo pulado não pode rodar: a CLI só executa o que
        está no manifesto.

    Raises:
        ConfigError: SHA-256 diferente, ZIP inválido ou manifesto que o modelo recusa.
    """
    skipped: Counter[str] = Counter()
    entries: list[NucleiTemplateEntry] = []
    with archive_path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != expected_sha256:
            raise ConfigError(
                "O SHA-256 do ZIP do catálogo difere do esperado.",
                hint="Baixe de novo o ZIP oficial da tag e confira o SHA-256.",
            )
        source.seek(0)
        try:
            with ZipFile(source) as archive:
                for member in _yaml_entries(archive):
                    path = member.filename.partition("/")[2]
                    if not path or member.file_size > _MAX_YAML_BYTES:
                        skipped["oversized" if path else "not_template"] += 1
                        continue
                    try:
                        entry = parse_template(path, archive.read(member))
                    except ConfigError:
                        skipped["unreadable"] += 1
                        continue
                    except ValidationError:
                        skipped["invalid_metadata"] += 1
                        continue
                    if entry is None:
                        skipped["not_template"] += 1
                    else:
                        entries.append(entry)
        except BadZipFile:
            raise ConfigError("O arquivo informado não é um ZIP válido.") from None
    try:
        manifest = NucleiManifest(
            nuclei_version=NUCLEI_VERSION,
            templates_version=TEMPLATES_VERSION,
            templates_archive_sha256=digest,
            entries=tuple(sorted(entries, key=lambda entry: entry.path)),
        )
    except ValidationError as error:
        raise ConfigError(
            f"O manifesto gerado é inválido ({error.error_count()} erro(s) do modelo)."
        ) from None
    return manifest, skipped


def write_manifest(manifest: NucleiManifest, output: Path) -> int:
    """Grava o manifesto comprimido e reproduzível; devolve o tamanho em bytes."""
    payload = manifest.model_dump_json().encode("utf-8")
    temporary = output.with_name(f".{output.name}.tmp")
    output.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 e sem nome: o mesmo catálogo gera sempre os mesmos bytes.
    with (
        temporary.open("wb") as handle,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=handle, compresslevel=_GZIP_LEVEL, mtime=0
        ) as compressed,
    ):
        compressed.write(payload)
    os.replace(temporary, output)
    return output.stat().st_size


def main(argv: Sequence[str] | None = None) -> None:
    """Valida o SHA-256 do ZIP e grava o manifesto."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="ZIP local da tag do nuclei-templates.")
    parser.add_argument("sha256", help="SHA-256 esperado do ZIP (64 dígitos hexadecimais).")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT, help="Arquivo de saída.")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.sha256):
        parser.error("Informe o SHA-256 esperado como 64 dígitos hexadecimais minúsculos.")
    if args.sha256 != TEMPLATES_ARCHIVE_SHA256:
        parser.error("O SHA-256 informado difere do fixado em nuclei_version.py.")
    try:
        manifest, skipped = build_manifest(args.archive, args.sha256)
        size = write_manifest(manifest, args.output)
    except ConfigError as error:
        parser.error(f"{error.message} {error.hint or ''}".strip())
    except (OSError, BadZipFile):
        parser.error("Confira o ZIP e a permissão de escrita do destino.")
    sys.stdout.write(
        f"{len(manifest.entries)} modelos, {size} bytes; pulados: {dict(sorted(skipped.items()))}\n"
    )


if __name__ == "__main__":
    main()
