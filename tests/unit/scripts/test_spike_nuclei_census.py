import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.profile import ProductProfile
from scripts.spike_nuclei_census import census
from tests.fakes.profile_data import valid_profile_data

_META = "id: fixture\ninfo:\n  tags: audit\n"


def _archive(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    path = tmp_path / "catalog.zip"
    with ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"catalog/{name}.yaml", text)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _get(*paths: str) -> str:
    entries = "".join(f'      - "{{{{BaseURL}}}}{path}"\n' for path in paths)
    return f"{_META}http:\n  - method: GET\n    path:\n{entries}"


def test_census_conta_modelo_inteiro_quando_algum_caminho_e_negado(tmp_path: Path) -> None:
    data = valid_profile_data()
    data["scope"]["allow"][0]["paths"].append("/catalog/**")
    data["scope"]["deny_paths"] = ["/catalog/denied"]
    profile = ProductProfile.from_data(data)
    path, digest = _archive(
        tmp_path,
        {
            "http/exposures/inside": _get("/catalog/inside"),
            "http/exposures/mixed": _get("/catalog/inside", "/catalog/denied", "/catalog/heapdump"),
            "http/exposures/dynamic": _get("/catalog/{{variable}}"),
        },
    )

    report = census(path, digest, [profile])

    assert report.whole_profile_matches == {profile.product: 1}
    assert report.statically_projectable == 2
    assert report.distinct_literal_get_exposure_paths == 2
    assert "/catalog/" not in report.model_dump_json()


@pytest.mark.parametrize(
    ("document", "reason"),
    [
        (_META + "dns: []\n", "not_http_only"),
        (_get("/health") + "dns: []\n", "not_http_only"),
        (_get("/health") + "    unsafe: false\n", "unsafe"),
        (_get("/health") + "    raw: []\n", "raw"),
        (_META + "code: []\n", "code"),
        (_META + "headless: []\n", "headless"),
        (_get("/{{interactsh-url}}"), "oast"),
        (_get("/health") + "    fuzzing: []\n", "dast"),
        (_get("/health").replace("audit", "DOS"), "tag:dos"),
        (_get("/health").replace("audit", "intrusive"), "tag:intrusive"),
        (_get("/health").replace("audit", "bruteforce"), "tag:bruteforce"),
        (_get("/health").replace("audit", "fuzz"), "tag:fuzz"),
        (_get("/health").replace("audit", "default-logins"), "tag:default-logins"),
    ],
)
def test_census_veta_modelo_quando_detecta_recurso_proibido(
    tmp_path: Path, document: str, reason: str
) -> None:
    path, digest = _archive(tmp_path, {"model": document})

    report = census(path, digest, [])

    assert report.veto_counts[reason] == 1
    assert report.after_vetoes == 0


def test_census_conta_yamls_que_nao_pode_classificar(tmp_path: Path) -> None:
    path, digest = _archive(
        tmp_path,
        {"missing": "", "malformed": "id: [", "config": "settings: true\n"},
    )

    report = census(path, digest, [])

    assert report.yaml_files == 3
    assert report.unreadable_yaml_files == 2
    assert report.templates == 0


def test_census_rejeita_zip_quando_sha256_diverge(tmp_path: Path) -> None:
    path, _ = _archive(tmp_path, {"model": _get("/health")})

    with pytest.raises(ConfigError, match="SHA-256"):
        census(path, "0" * 64, [])
