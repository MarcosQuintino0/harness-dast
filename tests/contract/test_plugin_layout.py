"""Contrato da pasta `plugin/` (ADR 0119): manifesto, hook, versão e fonte única dos arquivos."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
USE_SKILLS = ("onboard-product", "fix-reachability", "run-scan", "triage-findings", "test-product")
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


def test_plugin_hook_matcher_equals_the_repository_settings_matcher() -> None:
    plugin = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    assert (
        plugin["hooks"]["PreToolUse"][0]["matcher"]
        == (settings["hooks"]["PreToolUse"][0]["matcher"])
    )


def test_plugin_version_equals_the_pyproject_version() -> None:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["name"] == "hdast"
    assert manifest["version"] == project["project"]["version"]
    assert manifest["description"]


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
