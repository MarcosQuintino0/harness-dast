import re
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]


def test_wheel_inclui_compose_e_volumes_sem_pastas_do_checkout(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "Instale o uv para verificar o contrato do wheel."
    dist = tmp_path / "dist"
    result = subprocess.run(  # noqa: S603 - executável local com argumentos fixos, sem shell
        [
            uv,
            "build",
            "--offline",
            "--no-python-downloads",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--python",
            sys.executable,
            "--out-dir",
            str(dist),
            str(ROOT),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    (wheel_path,) = dist.glob("*.whl")
    with ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        compose = wheel.read("harness_dast/compose.yaml").decode()
        assert _relative_mounts(compose) == {"compose_data/policy", "compose_data/audit"}
        assert "harness_dast/compose_data/audit/README.txt" in names
        policy = wheel.read("harness_dast/compose_data/policy/policy.json").decode()
        original = ROOT / "docker/scope-proxy/policy/policy.json"
        assert policy.replace("\r\n", "\n") == original.read_text(encoding="utf-8")
        excluded = {"docker", "lab", "tests", "evals", "docs", ".claude"}
        assert all(
            excluded.isdisjoint(Path(name).parts[:-1]) or _adapter_file(name) for name in names
        )


def test_compose_empacotado_preserva_configuracao_do_clone() -> None:
    clone = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    packaged = (ROOT / "src/harness_dast/compose.yaml").read_text(encoding="utf-8")

    assert packaged == clone.replace("./docker/scope-proxy/", "./compose_data/")


def _relative_mounts(compose: str) -> set[str]:
    return set(re.findall(r"(?m)^ +-[ ]+\$\{[A-Z_]+:-\./([^}]+)\}:", compose))


def _adapter_file(name: str) -> bool:
    parts = Path(name).parts
    return parts[:3] == ("harness_dast", "adapters", "docker") and len(parts) == 4
