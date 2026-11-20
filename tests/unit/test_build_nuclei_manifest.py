import gzip
import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

import harness_dast.domain.nuclei_manifest as manifest_module
import scripts.build_nuclei_manifest as script
from harness_dast.adapters.nuclei.manifest_reader import load_nuclei_manifest
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.nuclei_manifest import NucleiManifest, NucleiTemplateEntry, veto_reasons

ROOT = "nuclei-templates-10.5.1/"

PLAIN = b"""id: plain-get
info:
  name: Plain
  severity: High
  tags: tech, Spring
http:
  - method: GET
    path:
      - "{{BaseURL}}/actuator/env"
"""
OLD_KEY = b"""id: old-key
info:
  name: Old
  severity: info
  tags: [exposure]
requests:
  - path:
      - "{{BaseURL}}/x"
"""
RAW_LEGIBLE = b"""id: raw-ok
info:
  name: Raw
  severity: medium
  tags: cve
http:
  - raw:
      - |
        POST /login HTTP/1.1
        Host: {{Hostname}}

        a=b
      - |
        GET /home HTTP/1.1
        Host: {{Hostname}}
"""
RAW_ILLEGIBLE = b"""id: raw-bad
info:
  name: Raw bad
  severity: low
http:
  - raw:
      - |
        {{verb}} /x HTTP/1.1
        Host: {{Hostname}}
"""
UNSAFE_OAST = b"""id: unsafe-oast
info:
  name: Unsafe
  severity: critical
http:
  - unsafe: true
    raw:
      - |
        GET /{{interactsh-url}} HTTP/1.1
"""
CODE = b"""id: code-one
info:
  name: Code
  severity: unheard
code:
  - engine: [bash]
    source: echo
"""
DNS_ONLY = b"""id: dns-one
info:
  name: Dns
  severity: info
dns:
  - name: "{{FQDN}}"
    type: A
"""
HELPER = b"""# arquivo de apoio, nao e modelo
severity: info
"""
BROKEN = b"id: [oops\ninfo: {\n"
FUZZ_DIR = b"""id: fuzz-xss
info:
  name: Fuzz
  severity: medium
http:
  - method: GET
    path:
      - "{{BaseURL}}/"
"""


def _make_zip(path: Path, files: dict[str, bytes]) -> str:
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(ROOT + name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    archive = tmp_path / "catalog.zip"
    digest = _make_zip(
        archive,
        {
            "http/misconfiguration/plain.yaml": PLAIN,
            "http/technologies/old.yaml": OLD_KEY,
            "http/cves/raw-ok.yaml": RAW_LEGIBLE,
            "http/cves/raw-bad.yaml": RAW_ILLEGIBLE,
            "http/vulnerabilities/unsafe-oast.yaml": UNSAFE_OAST,
            "code/code-one.yaml": CODE,
            "dns/dns-one.yaml": DNS_ONLY,
            "helpers/payloads.yaml": HELPER,
            "http/misconfiguration/broken.yaml": BROKEN,
            "dast/vulnerabilities/xss/fuzz-xss.yaml": FUZZ_DIR,
            "README.md": b"# nao yaml",
        },
    )
    # O modelo do manifesto só aceita o SHA-256 do catálogo real; o ZIP sintético usa o seu.
    monkeypatch.setattr(manifest_module, "TEMPLATES_ARCHIVE_SHA256", digest)
    monkeypatch.setattr(script, "TEMPLATES_ARCHIVE_SHA256", digest)
    return archive, digest


def _entries(manifest: NucleiManifest) -> dict[str, NucleiTemplateEntry]:
    return {entry.path: entry for entry in manifest.entries}


def test_build_manifest_le_metadados_de_modelo_valido(catalog: tuple[Path, str]) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)
    plain = _entries(manifest)["http/misconfiguration/plain.yaml"]

    assert plain.protocols == ("http",)
    assert plain.methods == ("GET",)
    assert plain.severity == "high"
    assert plain.tags == ("spring", "tech")
    assert plain.category == "misconfiguration"
    assert plain.sha256 == hashlib.sha256(PLAIN).hexdigest()
    assert (plain.unsafe, plain.raw, plain.oast, plain.dast) == (False,) * 4
    assert plain.unparsed_method is False
    assert veto_reasons(plain) == frozenset()


def test_build_manifest_aceita_o_nome_antigo_requests_como_http(catalog: tuple[Path, str]) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)

    old = _entries(manifest)["http/technologies/old.yaml"]
    assert old.protocols == ("http",)
    assert old.methods == ("GET",)


def test_build_manifest_le_o_metodo_da_primeira_linha_do_raw(catalog: tuple[Path, str]) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)

    raw = _entries(manifest)["http/cves/raw-ok.yaml"]
    assert raw.raw is True
    assert raw.methods == ("GET", "POST")
    assert raw.unparsed_method is False


def test_build_manifest_marca_unparsed_method_quando_o_raw_e_ilegivel(
    catalog: tuple[Path, str],
) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)

    bad = _entries(manifest)["http/cves/raw-bad.yaml"]
    assert bad.unparsed_method is True
    assert "unparsed_method" in {reason.value for reason in veto_reasons(bad)}


def test_build_manifest_marca_unsafe_oast_code_dast_e_protocolo(
    catalog: tuple[Path, str],
) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)
    entries = _entries(manifest)

    unsafe = entries["http/vulnerabilities/unsafe-oast.yaml"]
    assert unsafe.unsafe is True
    assert unsafe.oast is True
    assert entries["code/code-one.yaml"].code is True
    assert entries["code/code-one.yaml"].severity == "unknown"
    assert entries["dns/dns-one.yaml"].protocols == ("dns",)
    assert entries["dast/vulnerabilities/xss/fuzz-xss.yaml"].dast is True
    assert entries["dast/vulnerabilities/xss/fuzz-xss.yaml"].category is None


def test_build_manifest_pula_yaml_invalido_e_arquivo_de_apoio_e_conta(
    catalog: tuple[Path, str],
) -> None:
    archive, digest = catalog

    manifest, skipped = script.build_manifest(archive, digest)

    paths = set(_entries(manifest))
    assert "http/misconfiguration/broken.yaml" not in paths
    assert "helpers/payloads.yaml" not in paths
    assert skipped["unreadable"] == 1
    assert skipped["not_template"] == 1
    assert len(manifest.entries) == 8


def test_build_manifest_ordena_as_entradas_por_caminho(catalog: tuple[Path, str]) -> None:
    archive, digest = catalog

    manifest, _ = script.build_manifest(archive, digest)

    paths = [entry.path for entry in manifest.entries]
    assert paths == sorted(paths)


def test_build_manifest_recusa_sha256_divergente(catalog: tuple[Path, str]) -> None:
    archive, _ = catalog

    with pytest.raises(ConfigError, match="SHA-256"):
        script.build_manifest(archive, "0" * 64)


def test_build_manifest_recusa_arquivo_que_nao_e_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake.zip"
    fake.write_bytes(b"isto nao e um zip")

    with pytest.raises(ConfigError, match="ZIP"):
        script.build_manifest(fake, hashlib.sha256(fake.read_bytes()).hexdigest())


def test_build_manifest_recusa_zip_sem_nenhum_modelo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "empty.zip"
    digest = _make_zip(archive, {"README.md": b"x"})
    monkeypatch.setattr(manifest_module, "TEMPLATES_ARCHIVE_SHA256", digest)

    with pytest.raises(ConfigError, match="inválido"):
        script.build_manifest(archive, digest)


def test_main_grava_manifesto_reproduzivel_que_o_leitor_aceita(
    catalog: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive, digest = catalog
    first, second = tmp_path / "a.json.gz", tmp_path / "b.json.gz"

    script.main([str(archive), digest, "--output", str(first)])
    script.main([str(archive), digest, "--output", str(second)])

    assert first.read_bytes() == second.read_bytes()
    assert "8 modelos" in capsys.readouterr().out
    assert len(load_nuclei_manifest(first).entries) == 8
    assert gzip.decompress(first.read_bytes()).startswith(b"{")


def test_main_recusa_sha256_diferente_do_fixado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = tmp_path / "x.zip"
    digest = _make_zip(archive, {"a.yaml": PLAIN})

    with pytest.raises(SystemExit) as raised:
        script.main([str(archive), digest, "--output", str(tmp_path / "out.json.gz")])

    assert raised.value.code == 2
    assert "fixado" in capsys.readouterr().err
    assert not (tmp_path / "out.json.gz").exists()


def test_main_recusa_sha256_mal_formado(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        script.main([str(tmp_path / "x.zip"), "ABC"])

    assert raised.value.code == 2
