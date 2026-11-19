from pathlib import Path

import pytest

from evals.prepare_codespace import prepare_codespace
from evals.runner.cases import EvalError
from evals.runner.gitutil import changed_protected_paths, history, patch_of, snapshot
from tests.unit.evals.support import CASES, write

USE_SKILLS = ("onboard-product", "fix-reachability", "run-scan", "triage-findings", "test-product")


def test_prepare_entrega_copia_cega_sem_gabarito_git_ou_skills_extras(
    repo: Path, out: Path
) -> None:
    for skill in (*USE_SKILLS, "dev-blind-eval", "private-notes"):
        write(repo / "plugin" / "skills" / skill / "SKILL.md", "orientação")
    write(repo / "src/nested/.git/HEAD", "histórico aninhado")
    write(repo / "docs/desenvolver/rodada-cega-codespaces.md", "guia do coordenador")

    workspace = prepare_codespace("mini", "random", 7, out, source=repo, cases_dir=CASES).workspace

    assert (workspace / "EVAL-BRIEFING.md").is_file()
    assert (workspace / "inputs/openapi.json").is_file()
    assert not (workspace / "evals").exists()
    assert not list(workspace.rglob(".git"))
    assert not (workspace / "docs/desenvolver/rodada-cega-codespaces.md").exists()
    assert {path.name for path in (workspace / ".claude/skills").iterdir()} == set(USE_SKILLS)


def test_detecta_alteracao_de_arquivo_protegido_quando_git_fica_no_lacre(
    repo: Path, out: Path
) -> None:
    workspace = prepare_codespace("mini", "random", 7, out, source=repo, cases_dir=CASES).workspace
    write(workspace / "src/app.py", "adulterado")

    assert changed_protected_paths(workspace) == ["src/app.py"]


def test_mantem_historico_do_perfil_quando_git_fica_no_lacre(repo: Path, out: Path) -> None:
    workspace = prepare_codespace("mini", "random", 7, out, source=repo, cases_dir=CASES).workspace
    write(workspace / "products/mini/target.yml", "perfil sintético")

    commit = snapshot(workspace, "manual")

    assert [row["subject"] for row in history(workspace)] == [
        "base da rodada",
        "instantaneo: manual",
    ]
    assert "+perfil sintético" in patch_of(workspace, commit)
    assert not (workspace / ".git").exists()


def test_recusa_saida_quando_destino_fica_no_checkout(repo: Path) -> None:
    out = repo / "round"

    with pytest.raises(EvalError, match="fora do checkout"):
        prepare_codespace("mini", "random", 7, out, source=repo, cases_dir=CASES)

    assert not out.exists()


def test_recusa_caso_quando_nao_e_um_nome_versionado(repo: Path, out: Path) -> None:
    with pytest.raises(EvalError, match="Escolha um caso versionado"):
        prepare_codespace("../mini", "random", 7, out, source=repo, cases_dir=CASES)

    assert not out.exists()
