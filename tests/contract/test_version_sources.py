"""Versão publicada coerente e estado somente no roadmap."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_project_version_matches_latest_numbered_changelog_section() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    published = re.findall(
        r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M
    )
    assert published
    assert project["project"]["version"] == published[0]


@pytest.mark.parametrize("relative", ["README.md", "docs/architecture.md"])
def test_entry_documents_link_to_roadmap_instead_of_announcing_current_version(
    relative: str,
) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "roadmap.md" in text
    assert not re.search(r"estado atual[^\n]*\d+\.\d+", text, re.I)
