import re
from pathlib import Path

import pytest

from harness_dast.domain.nuclei_version import (
    NUCLEI_VERSION,
    TEMPLATES_ARCHIVE_SHA256,
    TEMPLATES_VERSION,
)

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]
NUCLEI_ZIP_SHA256 = "ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return (ROOT / "docker/nuclei/Dockerfile").read_text(encoding="utf-8")


def _arg(dockerfile: str, name: str) -> str:
    match = re.search(rf"^ARG {name}=(\S+)$", dockerfile, flags=re.MULTILINE)
    assert match is not None, name
    return match.group(1)


def test_dockerfile_fixa_as_versoes_e_os_sha256_de_nuclei_version(dockerfile: str) -> None:
    assert _arg(dockerfile, "NUCLEI_VERSION") == NUCLEI_VERSION
    assert _arg(dockerfile, "TEMPLATES_VERSION") == TEMPLATES_VERSION
    assert _arg(dockerfile, "TEMPLATES_SHA256") == TEMPLATES_ARCHIVE_SHA256
    assert _arg(dockerfile, "NUCLEI_SHA256") == NUCLEI_ZIP_SHA256


def test_dockerfile_fixa_a_base_por_digest(dockerfile: str) -> None:
    assert re.search(r"^ARG BASE=\S+@sha256:[0-9a-f]{64}$", dockerfile, flags=re.MULTILINE)


def test_dockerfile_confere_os_dois_downloads_e_so_usa_https(dockerfile: str) -> None:
    assert "sha256sum -c -" in dockerfile
    assert dockerfile.count("--proto '=https'") == 2
    assert "http://" not in dockerfile


def test_dockerfile_roda_sem_root_e_com_catalogo_somente_leitura(dockerfile: str) -> None:
    assert "USER 10002:10002" in dockerfile
    assert "adduser -D -u 10002" in dockerfile
    assert "chmod -R a-w,a+rX /opt/nuclei-templates" in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/nuclei"]' in dockerfile


def test_dockerfile_leva_o_rotulo_oci_de_versao(dockerfile: str) -> None:
    assert "LABEL org.opencontainers.image.version=$HDAST_IMAGE_VERSION" in dockerfile
