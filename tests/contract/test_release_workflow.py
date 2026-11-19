import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.contract
WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/images.yml"


@pytest.fixture
def workflow() -> dict[str | bool, Any]:
    data: dict[str | bool, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data


def test_release_publica_so_na_tag_depois_dos_digests(workflow: dict[str | bool, Any]) -> None:
    # O carregador YAML 1.1 interpreta a chave on como True.
    assert workflow.get("on", workflow.get(True)) == {"push": {"tags": ["v*"]}}
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    release = jobs["release"]
    assert release["needs"] == "images-lock"
    assert jobs["images-lock"]["needs"] == "publish"
    assert release["permissions"] == {"contents": "write"}
    assert all(
        job.get("permissions", {}).get("contents") != "write"
        for name, job in jobs.items()
        if name != "release"
    )

    checkout, download, validate, copy, build, publish = release["steps"]
    for step in release["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
    assert checkout["with"]["persist-credentials"] is False
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"]["name"] == "images-lock"
    assert "GITHUB_REF" in validate["run"]
    assert "cp " in copy["run"]
    assert "src/harness_dast/adapters/docker/" in copy["run"]
    assert '/bin/uv" build' in build["run"]
    assert publish["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "RELEASE_TAG": "${{ github.ref_name }}",
    }
    assert 'gh release create "$RELEASE_TAG" --verify-tag' in publish["run"]
    assert 'gh release upload "$RELEASE_TAG"' in publish["run"]
    assert all(extension in publish["run"] for extension in ("*.whl", "*.tar.gz"))


@pytest.mark.parametrize(
    ("tag", "lock_data", "valid"),
    [
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', True),
        ("refs/tags/v1.2.4", '{"version":"1.2.3"}', False),
        ("refs/heads/v1.2.3", '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", '{"version":"1.2.4"}', False),
        ("refs/tags/v1.2.3", "{}", False),
        ("refs/tags/v1.2.3", "{", False),
        ("refs/tags/v1.2.3", None, False),
    ],
)
def test_validacao_exige_versoes_iguais(
    workflow: dict[str | bool, Any], tmp_path: Path, tag: str, lock_data: str | None, valid: bool
) -> None:
    steps = workflow["jobs"]["release"]["steps"]
    command = next(step["run"] for step in steps if step.get("name") == "Conferir as três versões")
    first, *script, last = command.splitlines()
    assert (first, last) == ("python3 - <<'PY'", "PY")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    downloads = tmp_path / "images-lock"
    downloads.mkdir()
    if lock_data is not None:
        (downloads / "images.lock.json").write_text(lock_data, encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - executa só a validação local da release, sem shell
        [sys.executable, "-c", "\n".join(script)],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_REF": tag, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert (result.returncode == 0) is valid, result.stderr
