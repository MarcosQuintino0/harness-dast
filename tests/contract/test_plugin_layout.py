"""Contrato da pasta `plugin/` (ADR 0119): manifesto, hook, versão e fonte única dos arquivos."""

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from scripts.write_marketplace import MARKETPLACE_PATH, Marketplace

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
USE_SKILLS = (
    "onboard-product",
    "fix-reachability",
    "run-scan",
    "triage-findings",
    "test-product",
    "preparar",
)
AGENTS = ("spec-analyst", "findings-triager")


def _pre_tool_use(config: dict[str, object]) -> list[dict[str, object]]:
    hooks = config["hooks"]
    assert isinstance(hooks, dict)
    groups = hooks["PreToolUse"]
    assert isinstance(groups, list)
    return [hook for group in groups for hook in group["hooks"]]


def test_plugin_hooks_block_on_failure_and_use_the_plugin_root() -> None:
    config = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    hooks = _pre_tool_use(config)

    assert hooks
    for hook in hooks:
        assert hook["onFailure"] == "block"
        assert hook["timeout"] == 30
        assert "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py" in str(hook["command"])


def test_plugin_registers_a_bounded_session_start_hook() -> None:
    config = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert config["hooks"]["SessionStart"] == [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.sh"',
                    "timeout": 9,
                }
            ]
        }
    ]


def test_plugin_hook_matcher_equals_the_repository_settings_matcher() -> None:
    plugin = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    assert (
        plugin["hooks"]["PreToolUse"][0]["matcher"]
        == (settings["hooks"]["PreToolUse"][0]["matcher"])
    )


def _assert_versions_match(root: Path) -> None:
    plugin = root / "plugin/.claude-plugin/plugin.json"
    manifest = json.loads(plugin.read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    marketplace = Marketplace.model_validate_json((root / MARKETPLACE_PATH).read_text("utf-8"))

    assert manifest["name"] == "hdast"
    assert manifest["description"]
    version = project["project"]["version"]
    assert manifest["version"] == version, "A versão do plugin difere do pyproject.toml."
    assert marketplace.plugins[0].source.ref[1:] == version, "A ref difere do pyproject.toml."


def test_plugin_pyproject_and_marketplace_versions_match() -> None:
    _assert_versions_match(ROOT)


@pytest.mark.parametrize(
    ("relative_path", "previous", "replacement", "message"),
    [
        ("plugin/.claude-plugin/plugin.json", '"version": "', '"version": "0.', "versão do plugin"),
        (str(MARKETPLACE_PATH), '"ref": "v', '"ref": "v0.', "ref difere"),
    ],
)
def test_version_contract_rejects_divergence(
    tmp_path: Path, relative_path: str, previous: str, replacement: str, message: str
) -> None:
    for path in ("pyproject.toml", "plugin/.claude-plugin/plugin.json", str(MARKETPLACE_PATH)):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    target = tmp_path / relative_path
    content = target.read_text(encoding="utf-8").replace(previous, replacement, 1)
    target.write_text(content, encoding="utf-8")

    with pytest.raises(AssertionError, match=message):
        _assert_versions_match(tmp_path)


def test_marketplace_source_points_to_the_repository() -> None:
    path = ROOT / MARKETPLACE_PATH
    marketplace = Marketplace.model_validate_json(path.read_text(encoding="utf-8"))

    assert str(marketplace.plugins[0].source.url) == (
        "https://github.com/MarcosQuintino0/harness-dast.git"
    )


def test_use_skills_and_agents_live_only_in_the_plugin() -> None:
    for name in USE_SKILLS:
        assert (PLUGIN / "skills" / name / "SKILL.md").is_file()
        assert not (ROOT / ".claude" / "skills" / name).exists()
    for name in AGENTS:
        assert (PLUGIN / "agents" / f"{name}.md").is_file()
        assert not (ROOT / ".claude" / "agents" / f"{name}.md").exists()
    assert not list((PLUGIN / "skills").glob("dev-*"))


def test_guard_lives_only_in_the_plugin_and_settings_call_it_there() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    hooks = _pre_tool_use(settings)

    assert (PLUGIN / "hooks" / "guard.py").is_file()
    assert not (ROOT / ".claude" / "hooks" / "guard.py").exists()
    for hook in hooks:
        assert "plugin/hooks/guard.py" in str(hook["command"])
        assert hook["onFailure"] == "block"
