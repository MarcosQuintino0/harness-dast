"""Git local do workspace: base da rodada, instantaneos do perfil e deteccao de adulteracao."""

import subprocess
from pathlib import Path

from evals.runner.cases import EvalError, RoundDirs

_IDENTITY = ["-c", "user.name=eval-runner", "-c", "user.email=eval-runner@localhost"]
_QUIET = ["-c", "core.autocrlf=false", "-c", "core.safecrlf=false"]
PROTECTED = (
    "src/",
    ".claude/",
    "docker/",
    "compose.yaml",
    "lab/",
    "CLAUDE.md",
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    "products/_template/",
)


def _sealed_git_dir(workspace: Path) -> Path:
    return RoundDirs(workspace.parent).sealed / "workspace.git"


def git(workspace: Path, *args: str, git_dir: Path | None = None) -> str:
    """Roda `git` no workspace e devolve a saida padrao.

    Raises:
        EvalError: Git ausente ou comando com falha.
    """
    workspace = workspace.resolve()
    sealed_git = _sealed_git_dir(workspace)
    git_dir = git_dir or (sealed_git if sealed_git.is_dir() else workspace / ".git")
    command = [
        "git",
        f"--git-dir={git_dir.resolve()}",
        f"--work-tree={workspace}",
        *_IDENTITY,
        *_QUIET,
        *args,
    ]
    try:
        done = subprocess.run(  # noqa: S603 - argumentos fixos, sem shell
            command, cwd=workspace, capture_output=True, text=True, encoding="utf-8", check=False
        )
    except OSError as error:
        raise EvalError("git nao encontrado: instale o Git e confira o PATH.") from error
    if done.returncode != 0:
        raise EvalError(f"git {' '.join(args)} falhou: {done.stderr.strip()[:300]}")
    return done.stdout


def init_baseline(workspace: Path, *, separate_git: bool = False) -> str:
    """Inicia a base Git da rodada, guardando-a no lacre quando solicitado."""
    git_dir = _sealed_git_dir(workspace) if separate_git else None
    git(workspace, "init", "-q", "-b", "main", git_dir=git_dir)
    git(workspace, "add", "-A")
    git(workspace, "commit", "-q", "-m", "base da rodada", "--allow-empty")
    return git(workspace, "rev-parse", "HEAD").strip()


def snapshot(workspace: Path, label: str) -> str:
    """Commita o estado do perfil (`products/`, forcado porque o .gitignore o ignora)."""
    git(workspace, "add", "-A", "-f", "--", "products")
    git(workspace, "commit", "-q", "-m", f"instantaneo: {label}", "--allow-empty")
    return git(workspace, "rev-parse", "HEAD").strip()


def changed_protected_paths(workspace: Path) -> list[str]:
    """Caminhos protegidos (codigo, skills, permissoes, compose, lab) alterados desde a base."""
    out = git(workspace, "status", "--porcelain", "--untracked-files=all")
    paths = [line[3:].strip().strip('"') for line in out.splitlines() if len(line) > 3]
    return sorted(path for path in paths if path.startswith(PROTECTED))


def history(workspace: Path) -> list[dict[str, str]]:
    """Commits da rodada (do mais antigo ao mais novo): hash, instante e assunto."""
    out = git(workspace, "log", "--reverse", "--format=%H%x1f%cI%x1f%s")
    rows = [line.split("\x1f") for line in out.splitlines() if line]
    return [{"commit": row[0], "at": row[1], "subject": row[2]} for row in rows if len(row) == 3]


def patch_of(workspace: Path, commit: str) -> str:
    """Diff de um commit, restrito a `products/`."""
    return git(workspace, "show", "--format=", commit, "--", "products")
