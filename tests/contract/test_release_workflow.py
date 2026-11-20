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
    assert {
        name for name, job in jobs.items() if job.get("permissions", {}).get("contents") == "write"
    } == {"release", "marketplace"}

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
    ("tag", "lock_data", "plugin_data", "valid"),
    [
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', '{"version":"1.2.3"}', True),
        ("refs/tags/v1.2.4", '{"version":"1.2.3"}', '{"version":"1.2.3"}', False),
        ("refs/heads/v1.2.3", '{"version":"1.2.3"}', '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", '{"version":"1.2.4"}', '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", "{}", '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", "{", '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", None, '{"version":"1.2.3"}', False),
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', '{"version":"1.2.4"}', False),
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', "{}", False),
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', "{", False),
        ("refs/tags/v1.2.3", '{"version":"1.2.3"}', None, False),
    ],
)
def test_validacao_exige_versoes_iguais(
    workflow: dict[str | bool, Any],
    tmp_path: Path,
    tag: str,
    lock_data: str | None,
    plugin_data: str | None,
    valid: bool,
) -> None:
    steps = workflow["jobs"]["release"]["steps"]
    command = next(step["run"] for step in steps if step.get("id") == "versions")
    first, script = command.split("\n", 1)
    assert first == "python3 - <<'PY'"
    source, _ = script.split("\nPY\n", 1)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    downloads = tmp_path / "images-lock"
    downloads.mkdir()
    if lock_data is not None:
        (downloads / "images.lock.json").write_text(lock_data, encoding="utf-8")
    if plugin_data is not None:
        plugin = tmp_path / "plugin" / ".claude-plugin" / "plugin.json"
        plugin.parent.mkdir(parents=True)
        plugin.write_text(plugin_data, encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - executa só a validação local da release, sem shell
        [sys.executable, "-c", source],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_REF": tag, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert (result.returncode == 0) is valid, result.stderr


def test_marketplace_uses_minimal_permissions_and_pinned_actions(
    workflow: dict[str | bool, Any],
) -> None:
    jobs = workflow["jobs"]
    job = jobs["marketplace"]

    assert job["needs"] == "release"
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert {
        name
        for name, other in jobs.items()
        if other.get("permissions", {}).get("pull-requests") == "write"
    } == {"marketplace"}
    actions = [step["uses"] for step in job["steps"] if "uses" in step]
    assert actions
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in actions)


def test_marketplace_pushes_only_the_pull_request_branch(workflow: dict[str | bool, Any]) -> None:
    steps = workflow["jobs"]["marketplace"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    update = next(step for step in steps if "scripts/write_marketplace.py" in step.get("run", ""))
    commands = "\n".join(step.get("run", "") for step in steps)

    assert checkout["with"] == {"ref": "refs/heads/main", "persist-credentials": False}
    assert update["env"]["RELEASE_TAG"] == "${{ github.ref_name }}"
    assert update["env"]["RELEASE_SHA"] == "${{ needs.release.outputs.commit_sha }}"
    assert 'branch="chore/marketplace-$RELEASE_TAG"' in commands
    assert 'git switch -c "$branch"' in commands
    assert re.findall(r"\bgit push\b[^\n]*", commands) == [
        'git push origin "HEAD:refs/heads/$branch"'
    ]
    assert 'gh pr create --base main --head "$branch"' in commands
    release = workflow["jobs"]["release"]
    assert release["outputs"]["commit_sha"] == "${{ steps.versions.outputs.commit_sha }}"
    validation = next(step["run"] for step in release["steps"] if step.get("id") == "versions")
    assert "git rev-parse HEAD" in validation
