import json
from pathlib import Path

import pytest

from evals.runner.cases import EvalError, RoundDirs, load_case
from evals.runner.prepare import draw_secrets, prepare, resolve_mode
from tests.unit.evals.support import CASES, make_round, write


def test_prepare_copies_the_repo_without_what_reveals_the_flaws(repo: Path, out: Path) -> None:
    dirs = make_round(repo, out)

    kept = {
        p.relative_to(dirs.workspace).as_posix() for p in dirs.workspace.rglob("*") if p.is_file()
    }
    assert {"README.md", "src/app.py", "docs/ok.md", "lab/mini/compose.yaml"} <= kept
    assert "inputs/openapi.json" in kept
    assert "products/_template/target.yml" in kept
    for gone in (
        "evals/answer-keys/k.md",
        "tests/integration/t.py",
        "docs/reviews/r.md",
        "docs/guides/primeiro-uso.md",
        "lab/README.md",
        "lab/mini/openapi.json",
        "lab/mini/secret-notes/n.md",
        "products/real-profile/target.yml",
        "runs/old/run.json",
        ".venv/lib.py",
        "src/__pycache__/x.pyc",
    ):
        assert gone not in kept
    assert "main" in (dirs.workspace / ".git" / "HEAD").read_text(encoding="utf-8")


def test_prepare_writes_the_stub_dockerfile_and_the_briefing_without_flaw_terms(
    repo: Path, out: Path
) -> None:
    dirs = make_round(repo, out)

    assert (dirs.workspace / "lab/mini/Dockerfile").read_text(encoding="utf-8") == "FROM mini:1\n"
    briefing = (dirs.workspace / "EVAL-BRIEFING.md").read_text(encoding="utf-8")
    assert "MINI-1" in briefing
    assert "decision-log.md" in briefing
    assert "hdast cleanup" in briefing
    for term in load_case("mini", CASES).leak_terms:
        assert term not in briefing
    assert "SQL" not in briefing


@pytest.mark.parametrize(("mode", "value"), [("vulnerable", "1"), ("secure", "0")])
def test_prepare_seals_the_mode_outside_the_workspace_and_gives_it_only_to_the_agent_env(
    repo: Path, out: Path, mode: str, value: str
) -> None:
    dirs = make_round(repo, out, mode)

    sealed = json.loads((dirs.sealed / "mode.json").read_text(encoding="utf-8"))
    env = json.loads((dirs.sealed / "agent-env.json").read_text(encoding="utf-8"))
    assert sealed["mode"] == mode
    assert env["MINI_VULNERABLE"] == value
    assert not list(dirs.workspace.rglob(".env"))
    assert not any(
        "MINI_VULNERABLE" in p.read_text(encoding="utf-8", errors="ignore")
        for p in dirs.workspace.rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    assert dirs.sealed not in dirs.workspace.parents
    assert not list(dirs.workspace.rglob("mode.json"))


def test_prepare_denies_docker_and_env_inspection_in_the_workspace_settings_only(
    repo: Path, out: Path
) -> None:
    write(repo / ".claude/settings.json", json.dumps({"permissions": {"deny": ["WebFetch"]}}))

    dirs = make_round(repo, out)

    deny = json.loads((dirs.workspace / ".claude/settings.json").read_text(encoding="utf-8"))[
        "permissions"
    ]["deny"]
    assert {"WebFetch", "Bash(docker:*)", "Bash(env:*)"} <= set(deny)
    original = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
    assert original["permissions"]["deny"] == ["WebFetch"]


def test_random_mode_is_reproducible_by_seed_and_uses_both_modes() -> None:
    case = load_case("mini", CASES)

    draws = {resolve_mode(case, "random", seed) for seed in range(20)}

    assert draws == {"vulnerable", "secure"}
    assert resolve_mode(case, "random", 5) == resolve_mode(case, "random", 5)


def test_unknown_mode_is_refused() -> None:
    with pytest.raises(EvalError, match="invalido"):
        resolve_mode(load_case("mini", CASES), "easy", 1)


def test_prepare_refuses_a_term_from_the_answer_key_left_in_the_copy(repo: Path, out: Path) -> None:
    write(repo / "docs/leaky.md", "aqui esta o segredo-do-gabarito inteiro")

    with pytest.raises(EvalError, match="termo"):
        prepare("mini", "vulnerable", 1, out, source=repo, cases_dir=CASES)
    report = json.loads((RoundDirs(out).sealed / "leak-report.json").read_text(encoding="utf-8"))
    assert report[0]["path"] == "docs/leaky.md"


def test_prepare_refuses_a_folder_that_is_not_empty(repo: Path, out: Path) -> None:
    write(out / "algo.txt", "x")

    with pytest.raises(EvalError, match="nao esta vazia"):
        prepare("mini", "vulnerable", 1, out, source=repo, cases_dir=CASES)


def test_prepare_starts_a_local_git_baseline_in_the_workspace(repo: Path, out: Path) -> None:
    dirs = make_round(repo, out)

    assert (dirs.workspace / ".git").is_dir()


def test_draw_secrets_generates_fresh_values_and_keeps_the_fixed_ones() -> None:
    case = load_case("mini", CASES)

    first, second = draw_secrets(case), draw_secrets(case)

    assert set(first) == {"MINI_ADMIN_USER", "MINI_ADMIN_PASS"}
    assert first["MINI_ADMIN_USER"].startswith("lab_")
    assert first != second


def test_real_cases_load_and_list_their_flaws() -> None:
    for name in ("clinica-piloto", "vampi"):
        case = load_case(name)

        assert case.flaws
        assert any(flaw.detectable for flaw in case.flaws)
        assert case.leak_terms


def test_unknown_case_names_the_known_ones() -> None:
    with pytest.raises(EvalError, match="clinica-piloto"):
        load_case("nao-existe")


def test_prepare_leaves_other_agents_worktrees_out_of_the_copy(repo: Path, out: Path) -> None:
    leaked = repo / ".claude" / "worktrees" / "agent-x" / "evals" / "answer-keys" / "k.md"
    leaked.parent.mkdir(parents=True)
    leaked.write_text("gabarito\n", encoding="utf-8")

    dirs = make_round(repo, out)

    assert not (dirs.workspace / ".claude" / "worktrees").exists()


def test_prepare_copies_agents_instructions_without_coordinator_material(
    repo: Path, out: Path
) -> None:
    instructions = (Path(__file__).resolve().parents[3] / "AGENTS.md").read_text(encoding="utf-8")
    write(repo / "AGENTS.md", instructions)
    write(repo / "docs/plans/briefing.md", "segredo-do-gabarito")
    write(repo / ".claude/settings.local.json", "permissoes do coordenador")
    write(repo / ".claude/worktrees/agent/evals/answer-keys/key.md", "gabarito")

    dirs = make_round(repo, out)

    assert (dirs.workspace / "AGENTS.md").read_text(encoding="utf-8") == instructions
    assert not (dirs.workspace / "docs/plans").exists()
    assert not (dirs.workspace / ".claude/settings.local.json").exists()
    assert not (dirs.workspace / ".claude/worktrees").exists()
    assert not (dirs.workspace / "evals/answer-keys").exists()


def test_prepare_detects_answer_key_term_in_agents_instructions(repo: Path, out: Path) -> None:
    write(repo / "AGENTS.md", "segredo-do-gabarito")

    with pytest.raises(EvalError, match="termo"):
        prepare("mini", "vulnerable", 1, out, source=repo, cases_dir=CASES)

    report = json.loads((RoundDirs(out).sealed / "leak-report.json").read_text(encoding="utf-8"))
    assert any(hit["path"] == "AGENTS.md" for hit in report)
