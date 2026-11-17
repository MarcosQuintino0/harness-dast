"""A cópia cega entrega só contexto operacional explicitamente permitido."""

import json
import re
from pathlib import Path

import pytest

from evals.runner.exclusions import exclusions_for, walk_kept
from evals.runner.gitutil import changed_protected_paths, git
from evals.runner.prepare import copy_workspace
from tests.unit.evals.support import CASES, make_round, write

ROOT = Path(__file__).resolve().parents[3]
USE_SKILLS = ("onboard-product", "fix-reachability", "run-scan", "triage-findings", "test-product")


@pytest.mark.parametrize(
    "relative",
    [
        "unknown-project/notes.md",
        "sites/index.html",
        "translate-app/app.py",
        ".claude/skills/dev-new/SKILL.md",
        "CHANGELOG.md",
        "docs/roadmap.md",
        "docs/research/study.md",
        "tests/unit/test_lab_expectations.py",
        "products/real/target.yml",
        "src/.env.local",
    ],
)
def test_unapproved_context_is_not_copied(repo: Path, out: Path, relative: str) -> None:
    write(repo / relative, "segredo-do-gabarito")

    dirs = make_round(repo, out)

    assert not (dirs.workspace / relative).exists()


def test_real_operational_skills_and_shared_rules_are_kept_without_version_history() -> None:
    from evals.runner.cases import load_case

    kept = dict((rel, path) for path, rel in walk_kept(ROOT, exclusions_for(load_case("vampi"))))

    for name in USE_SKILLS:
        assert f".claude/skills/{name}/SKILL.md" in kept
    assert not any(p.startswith(".claude/skills/dev-") for p in kept)
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = kept[name].read_text(encoding="utf-8")
        assert not re.search(r"(?m)^(?:Estado:|(?:A\s+)?V\d+\.)", text)
        assert "BOLA entre pacientes preservado" not in text
        assert "## Notas de entrega" not in text


def test_manifest_counts_exactly_the_copied_repository_files(repo: Path, out: Path) -> None:
    from evals.runner.cases import load_case

    workspace = out / "workspace"
    copy_workspace(load_case("mini", CASES), repo, workspace)

    manifest = json.loads((out / "sealed/workspace-manifest.json").read_text(encoding="utf-8"))
    copied = [p for p in workspace.rglob("*") if p.is_file()]
    assert manifest["policy"] == "allowlist-v1"
    assert manifest["stage"] == "repository-copy"
    assert manifest["total_files"] == len(copied)
    assert sum(manifest["roots"].values()) == len(copied)
    assert manifest["roots"]["products/_template"] == 1
    assert "tests" not in manifest["roots"]


def test_shared_rules_are_protected_against_tampering(repo: Path, out: Path) -> None:
    write(repo / "AGENTS.md", "regras")
    dirs = make_round(repo, out)
    write(dirs.workspace / "AGENTS.md", "adulterado")

    assert "AGENTS.md" in changed_protected_paths(dirs.workspace)
    assert "AGENTS.md" in git(dirs.workspace, "diff", "--name-only")
