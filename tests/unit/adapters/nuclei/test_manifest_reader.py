import gzip
import json
from pathlib import Path

import pytest

from harness_dast.adapters.nuclei.manifest_reader import MANIFEST_PATH, load_nuclei_manifest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)


def _entry(path: str = "http/misconfiguration/a.yaml") -> dict[str, object]:
    return {
        "path": path,
        "sha256": "a" * 64,
        "protocols": ["http"],
        "methods": ["GET"],
        "unsafe": False,
        "raw": False,
        "code": False,
        "headless": False,
        "oast": False,
        "dast": False,
        "unparsed_method": False,
        "tags": ["spring"],
        "severity": "info",
        "category": "misconfiguration",
    }


def _document(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "nuclei_version": NUCLEI_VERSION,
        "templates_version": TEMPLATES_VERSION,
        "templates_archive_sha256": TEMPLATES_ARCHIVE_SHA256,
        "entries": [_entry()],
    }
    return {**base, **changes}


def _write(path: Path, document: object) -> Path:
    path.write_bytes(gzip.compress(json.dumps(document).encode("utf-8")))
    return path


def test_load_nuclei_manifest_le_arquivo_valido(tmp_path: Path) -> None:
    path = _write(tmp_path / "m.json.gz", _document())

    manifest = load_nuclei_manifest(path)

    assert [entry.path for entry in manifest.entries] == ["http/misconfiguration/a.yaml"]


def test_load_nuclei_manifest_recusa_arquivo_ausente(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não está no pacote"):
        load_nuclei_manifest(tmp_path / "ausente.json.gz")


def test_load_nuclei_manifest_recusa_arquivo_que_nao_e_gzip(tmp_path: Path) -> None:
    path = tmp_path / "m.json.gz"
    path.write_bytes(b"isto nao e gzip")

    with pytest.raises(ConfigError, match="corrompido"):
        load_nuclei_manifest(path)


def test_load_nuclei_manifest_recusa_gzip_truncado(tmp_path: Path) -> None:
    path = tmp_path / "m.json.gz"
    path.write_bytes(gzip.compress(json.dumps(_document()).encode("utf-8"))[:-12])

    with pytest.raises(ConfigError, match="corrompido"):
        load_nuclei_manifest(path)


def test_load_nuclei_manifest_recusa_json_malformado(tmp_path: Path) -> None:
    path = tmp_path / "m.json.gz"
    path.write_bytes(gzip.compress(b"{nao e json"))

    with pytest.raises(ConfigError, match="inválido"):
        load_nuclei_manifest(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"templates_version": "9.0.0"},
        {"nuclei_version": "3.0.0"},
        {"templates_archive_sha256": "b" * 64},
        {"entries": []},
        {"entries": [_entry(), _entry()]},
        {"schema_version": 2},
    ],
)
def test_load_nuclei_manifest_recusa_outra_versao_ou_conteudo_invalido(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    path = _write(tmp_path / "m.json.gz", _document(**changes))

    with pytest.raises(ConfigError, match="inválido ou de outra versão"):
        load_nuclei_manifest(path)


def test_load_nuclei_manifest_recusa_destino_que_e_pasta(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Não consegui ler"):
        load_nuclei_manifest(tmp_path)


def test_manifesto_empacotado_quando_presente_confere_com_nuclei_version() -> None:
    if not MANIFEST_PATH.is_file():
        pytest.skip("manifesto ainda não gerado no pacote")

    manifest = load_nuclei_manifest()

    assert manifest.templates_archive_sha256 == TEMPLATES_ARCHIVE_SHA256
    assert manifest.templates_version == TEMPLATES_VERSION
