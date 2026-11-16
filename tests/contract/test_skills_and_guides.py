"""Contrato das skills, subagentes, permissões e guias do M6 com a CLI real.

Skills e guias não podem prometer comando nem flag que não existe: toda ocorrência de `hdast ...`
dentro de código (bloco cercado ou trecho em linha) é conferida contra o app Typer. Também confere a
forma de cada skill (frontmatter, seções obrigatórias, tamanho), as ferramentas dos subagentes e as
permissões de `.claude/settings.json`.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import typer.main
import yaml

from harness_dast.cli.app import build_app

ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
AGENT_FILES = sorted((ROOT / ".claude" / "agents").glob("*.md"))
GUIDE_FILES = sorted((ROOT / "docs" / "guides").glob("*.md"))
EXTRA_FILES = [ROOT / "evals" / "README.md", ROOT / "README.md"]
CHECKED_FILES = [*SKILL_FILES, *AGENT_FILES, *GUIDE_FILES, *EXTRA_FILES]
STAGE_SKILLS = ("onboard-product", "fix-reachability", "run-scan", "triage-findings")
EXPECTED_SKILLS = {*STAGE_SKILLS, "test-product"}
EXPECTED_AGENTS = {"spec-analyst", "findings-triager"}

_FENCE = re.compile(r"^```.*?\n(.*?)^```", re.DOTALL | re.MULTILINE)
_INLINE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_HDAST = re.compile(r"(?<![\w/.\-])hdast(?= |$)")
_STOP = re.compile(r"\||;|&&|#|>|`")


def _commands() -> dict[tuple[str, ...], Any]:
    root = typer.main.get_command(build_app())
    found: dict[tuple[str, ...], Any] = {}

    def walk(command: Any, prefix: tuple[str, ...]) -> None:
        if prefix:
            found[prefix] = command
        for name, sub in getattr(command, "commands", {}).items():
            walk(sub, (*prefix, name))

    walk(root, ())
    return found


def _flags_of(command: Any) -> set[str]:
    flags = {"--json", "--help"}
    for param in command.params:
        flags.update(opt for opt in [*param.opts, *param.secondary_opts] if opt.startswith("--"))
    return flags


def _code_lines(text: str) -> list[str]:
    lines: list[str] = []
    for block in _FENCE.findall(text):
        lines.extend(block.splitlines())
    without_fences = _FENCE.sub("", text)
    for line in without_fences.splitlines():
        lines.extend(_INLINE.findall(line))
    return lines


def _invocations(path: Path) -> list[list[str]]:
    """Tokens que seguem cada `hdast` dentro de código, até um separador de shell."""
    found: list[list[str]] = []
    for line in _code_lines(path.read_text(encoding="utf-8")):
        for match in _HDAST.finditer(line):
            rest = _STOP.split(line[match.end() :])[0]
            tokens = [item.strip("\"',;:.()") for item in rest.split()]
            found.append([item for item in tokens if item])
    return found


def _check(tokens: list[str], commands: dict[tuple[str, ...], Any]) -> str | None:
    words = [item for item in tokens if item != "--json"]
    positional = [item for item in words if not item.startswith("-")]
    if not positional:
        return None if not words or words[0] in {"--help"} else "sem comando"
    first = positional[0]
    if not re.fullmatch(r"[a-z][a-z-]*", first):
        return None
    top = {path[0] for path in commands}
    if first not in top:
        return f"comando inexistente: {first}"
    path: tuple[str, ...] = (first,)
    if (first, "up") in commands or any(key[0] == first and len(key) == 2 for key in commands):
        sub = positional[1] if len(positional) > 1 else ""
        if not any(key == (first, sub) for key in commands):
            return f"subcomando inexistente: {first} {sub}"
        path = (first, sub)
    allowed = _flags_of(commands[path])
    for item in words:
        if item.startswith("--"):
            flag = item.split("=", 1)[0]
            if flag not in allowed:
                return f"flag inexistente em {' '.join(path)}: {flag}"
    return None


def test_checked_files_exist() -> None:
    assert {path.parent.name for path in SKILL_FILES} == EXPECTED_SKILLS
    assert {path.stem for path in AGENT_FILES} == EXPECTED_AGENTS
    assert len(GUIDE_FILES) >= 6


@pytest.mark.parametrize("path", CHECKED_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_hdast_command_cited_exists_with_its_flags(path: Path) -> None:
    commands = _commands()
    problems = [
        f"{' '.join(tokens)!r}: {message}"
        for tokens in _invocations(path)
        if (message := _check(tokens, commands))
    ]

    assert not problems, "\n".join(problems)


def test_the_extractor_finds_commands_and_rejects_invented_ones() -> None:
    commands = _commands()

    assert _check(["--json", "stack", "up", "<produto>", "--secure"], commands) is None
    assert _check(["probe", "<p>", "--include-delete"], commands) is None
    assert _check(["cleanup", "<p>", "--confirm", "X"], commands) is not None
    assert _check(["stack", "restart"], commands) is not None
    assert _check(["rodar", "tudo"], commands) is not None
    assert sum(len(_invocations(path)) for path in SKILL_FILES) >= 15


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: sem frontmatter"
    loaded = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_name_when_to_use_numbered_steps_table_and_never_section(path: Path) -> None:
    meta = _frontmatter(path)
    text = path.read_text(encoding="utf-8")

    assert meta["name"] == path.parent.name
    description = str(meta["description"])
    assert description.startswith("Use quando")
    assert len(text.splitlines()) < 150
    assert re.search(r"^1\. \*\*", text, flags=re.MULTILINE)
    assert "## Se der X, faça Y" in text
    assert re.search(r"^\| .* \|$", text.split("## Se der X, faça Y")[1], flags=re.MULTILINE)
    assert "## Nunca" in text
    assert "decision-log.md" in text
    never = text.split("## Nunca")[1]
    assert ".env" in never or "cleanup" in never


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_repeats_the_part_b_locks_that_apply_to_it(path: Path) -> None:
    never = path.read_text(encoding="utf-8").split("## Nunca")[1]
    name = path.parent.name

    assert "curl" in never or name == "run-scan"
    assert "cleanup" in never or "limpeza" in never
    if name in {"onboard-product", "run-scan", "test-product"}:
        assert "escopo" in never


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_subagent_has_minimal_tools_and_never_web_or_shell(path: Path) -> None:
    meta = _frontmatter(path)
    tools = {item.strip() for item in str(meta["tools"]).split(",")}

    assert meta["name"] == path.stem
    assert str(meta["description"])
    assert tools <= {"Read", "Grep", "Glob"}
    assert not tools & {"Bash", "WebFetch", "WebSearch", "Write", "Edit", "PowerShell"}


def _permissions() -> dict[str, list[str]]:
    data = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    permissions = data["permissions"]
    assert set(permissions) <= {"allow", "deny", "ask"}
    return {key: list(value) for key, value in permissions.items()}


def test_settings_allow_only_hdast_and_deny_the_dangerous_commands() -> None:
    permissions = _permissions()
    allow, deny = permissions["allow"], permissions["deny"]

    assert set(allow) == {"Bash(uv run hdast:*)", "Bash(hdast:*)"}
    for rule in (
        "Bash(curl:*)",
        "Bash(wget:*)",
        "Bash(hdast cleanup:*)",
        "Bash(uv run hdast cleanup:*)",
        "WebFetch",
        "Read(**/.env*)",
        "Read(!.env.example)",
        "Edit(products/*/cleanup/**)",
    ):
        assert rule in deny


def test_settings_deny_the_agent_from_writing_or_removing_secrets_in_every_spelling() -> None:
    deny = set(_permissions()["deny"])

    for shell in ("Bash", "PowerShell"):
        for sub in ("set", "delete"):
            for prefix in ("uv run hdast", "uv run hdast --json", "hdast", "hdast --json"):
                assert f"{shell}({prefix} secret {sub}:*)" in deny


def test_settings_do_not_deny_listing_secrets_and_never_allow_set_or_delete() -> None:
    permissions = _permissions()

    assert not [rule for rule in permissions["deny"] if "secret list" in rule]
    assert not [rule for rule in permissions["allow"] if "secret" in rule]


def test_settings_deny_precedes_exception_for_env_example() -> None:
    deny = _permissions()["deny"]

    assert deny.index("Read(**/.env*)") < deny.index("Read(!.env.example)")


def test_settings_never_allow_cleanup_in_any_spelling() -> None:
    allow = _permissions()["allow"]

    assert not [rule for rule in allow if "cleanup" in rule]


def _leak_terms() -> list[str]:
    terms: list[str] = []
    for case_file in sorted((ROOT / "evals" / "cases").glob("*/case.yml")):
        loaded = yaml.safe_load(case_file.read_text(encoding="utf-8"))
        terms.extend(str(term) for term in loaded.get("leak_terms", []))
    return terms


def test_skills_guides_and_agents_do_not_leak_planted_flaw_terms() -> None:
    terms = _leak_terms()
    assert terms, "os casos precisam declarar leak_terms"
    leaks: list[str] = []
    for path in [*SKILL_FILES, *AGENT_FILES, *GUIDE_FILES, ROOT / "README.md"]:
        text = path.read_text(encoding="utf-8")
        leaks.extend(
            f"{path.relative_to(ROOT)}: {term}"
            for term in terms
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE)
        )

    assert not leaks, "\n".join(leaks)


def _skill_text(name: str) -> str:
    return (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_test_product_points_to_the_four_stage_skills_in_order() -> None:
    text = _skill_text("test-product")

    positions = [text.index(f"`{name}`") for name in STAGE_SKILLS]
    assert positions == sorted(positions)
    steps = text.split("## Passos")[1].split("## Se der X")[0]
    stage_order = [steps.index(name) for name in STAGE_SKILLS]
    assert stage_order == sorted(stage_order)


def test_test_product_distinguishes_partial_reachability_from_safety_stops() -> None:
    text = _skill_text("test-product").split("## Se der X")[1].split("## Diário")[0]

    for case in (
        "Falta dado da carta",
        "Alcançabilidade abaixo da meta",
        "achado de severidade alta",
        "dúvida de autorização, escopo ou janela",
    ):
        assert case in text
    reachability = next(line for line in text.splitlines() if "Alcançabilidade abaixo" in line)
    assert "varredura parcial" in reachability
    assert "motivos do último `probe`" in reachability
    assert "Pare;" not in reachability


def test_reachability_local_failures_do_not_stop_the_whole_flow() -> None:
    text = _skill_text("fix-reachability")
    lines = text.splitlines()
    auth = next(line for line in lines if line.startswith("| `auth_error`"))
    server = next(line for line in lines if line.startswith("| `server_error`"))
    for line in (auth, server):
        assert "só essa operação" in line
        assert "diário" in line
        assert "lacunas" in line
    assert "contas da carta" in auth
    assert "auth_rejected_expected" in text
    assert "bloqueia mais operações" in text


def test_test_product_cites_every_part_b_lock_and_does_not_restate_stage_rules() -> None:
    text = _skill_text("test-product")
    never = text.split("## Nunca")[1]

    assert "Parte B" in never
    for lock in ("curl", ".env", "hdast cleanup", "escopo", "severidade", "dados sintéticos"):
        assert lock in never
    assert "0,9" not in text
    assert "6 execuções" not in text


def test_test_product_hands_over_the_html_report_and_groups() -> None:
    text = _skill_text("test-product")

    assert "report.html" in text
    assert "groups" in text


def test_test_product_starts_with_doctor_and_runs_authz_by_default_read_only() -> None:
    text = _skill_text("test-product")

    assert text.index("hdast doctor") < text.index("## Passos")
    assert "--no-authz" in text
    assert "authz.allow_writes" in text
    assert "duas contas do mesmo papel" in text
    assert "--skip-scan" in text


def test_onboard_product_asks_whether_the_letter_authorizes_authz_writes() -> None:
    text = _skill_text("onboard-product")

    assert "allow_authz_writes" in text
    assert "AUTHZ_WRITES_AUTHORIZED" in text
    assert "Não sei" in text


def test_run_scan_says_authz_comes_on_and_never_turns_writes_on() -> None:
    text = _skill_text("run-scan")

    assert "--no-authz" in text
    assert "authz.allow_writes" in text


def test_test_product_never_turns_wide_path_mode_on_by_itself() -> None:
    text = _skill_text("test-product")

    assert "Não** ligue `scope.path_mode: wide`" in text
    assert "carta" in text.split("scope.path_mode: wide")[1][:200]


@pytest.mark.parametrize("name", ["docs/guides/primeiro-uso.md", "README.md"])
def test_guides_start_with_doctor_and_mention_authz_and_the_wide_mode_rule(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")

    assert "hdast doctor" in text
    assert "--authz" in text
    assert "duas contas do mesmo papel" in text or "path_mode: wide" in text


@pytest.mark.parametrize("command", ["doctor", "authz", "run --authz"])
def test_settings_cover_the_v1_1_commands_with_the_same_hdast_rules_and_no_new_denial(
    command: str,
) -> None:
    permissions = _permissions()
    prefixes = [rule.removeprefix("Bash(").removesuffix(":*)") for rule in permissions["allow"]]
    line = f"uv run hdast --json {command} produto"

    assert any(line.startswith(prefix) for prefix in prefixes)
    for rule in permissions["deny"]:
        if rule.startswith("Bash(") and rule.endswith(":*)"):
            assert not line.startswith(rule.removeprefix("Bash(").removesuffix(":*)"))
