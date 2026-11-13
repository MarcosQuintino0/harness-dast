"""`collect`: junta o rastro da rodada em `<out>/trace/`."""

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from evals.runner import gitutil
from evals.runner.cases import CASES_DIR, EvalError, RoundDirs, load_case

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
STATE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class CollectResult:
    """Resumo da coleta."""

    trace: Path
    copied: tuple[str, ...]
    problems: tuple[str, ...]


def fetch_target_state(url: str) -> dict[str, object]:
    """Le o estado do alvo na porta de gestao do laboratorio (so loopback; so o executor chama).

    Raises:
        EvalError: URL fora do loopback ou alvo inacessivel.
    """
    parts = urlsplit(url)
    if parts.scheme != "http" or (parts.hostname or "") not in LOOPBACK:
        raise EvalError(f"URL de estado fora do loopback: {url}.")
    try:
        with urllib.request.urlopen(url, timeout=STATE_TIMEOUT_SECONDS) as response:  # noqa: S310 - esquema e host conferidos acima
            loaded = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise EvalError(f"Nao li o estado do alvo em {url}: {error}.") from error
    if not isinstance(loaded, dict):
        raise EvalError(f"Estado do alvo em {url} nao e um objeto JSON.")
    return loaded


def _copy_tree(source: Path, target: Path) -> bool:
    if not source.is_dir():
        return False
    shutil.copytree(source, target, dirs_exist_ok=True)
    return True


def _copy_profiles(workspace: Path, trace: Path) -> list[str]:
    copied: list[str] = []
    products = workspace / "products"
    if products.is_dir():
        for entry in sorted(products.iterdir()):
            if entry.is_dir() and entry.name != "_template":
                _copy_tree(entry, trace / "profile" / "final" / entry.name)
                copied.append(f"profile/final/{entry.name}")
    return copied


def _copy_history(workspace: Path, trace: Path) -> int:
    commits = gitutil.history(workspace)
    folder = trace / "profile" / "history"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "history.json").write_text(json.dumps(commits, indent=2), encoding="utf-8")
    for index, row in enumerate(commits):
        patch = gitutil.patch_of(workspace, row["commit"])
        (folder / f"{index:03d}-{row['commit'][:8]}.patch").write_text(patch, encoding="utf-8")
    return len(commits)


def _copy_proxy_audit(state: Path, trace: Path) -> list[str]:
    copied: list[str] = []
    for audit in sorted((state / "stacks").glob("*/audit/audit.jsonl")):
        stack = audit.parent.parent.name
        target = trace / "proxy-audit" / stack / "audit.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audit, target)
        copied.append(f"proxy-audit/{stack}")
    return copied


def _write_state(case_url: str | None, trace: Path, problems: list[str]) -> bool:
    if case_url is None:
        return False
    try:
        state = fetch_target_state(case_url)
    except EvalError as error:
        (trace / "target-state.error.txt").write_text(str(error), encoding="utf-8")
        problems.append(str(error))
        return False
    (trace / "target-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return True


def collect(
    out: Path, *, state_dir: Path | None = None, cases_dir: Path = CASES_DIR
) -> CollectResult:
    """Coleta o rastro da rodada.

    Raises:
        EvalError: `<out>` nao e uma rodada preparada.
    """
    dirs = RoundDirs(out)
    mode_file = dirs.sealed / "mode.json"
    if not mode_file.is_file() or not dirs.workspace.is_dir():
        raise EvalError(f"{out} nao e uma rodada preparada (falta sealed/mode.json ou workspace/).")
    case = load_case(json.loads(mode_file.read_text(encoding="utf-8"))["case"], cases_dir)
    trace = dirs.trace
    trace.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    copied: list[str] = []
    tamper = gitutil.changed_protected_paths(dirs.workspace)
    gitutil.snapshot(dirs.workspace, "coleta")
    (trace / "tamper.json").write_text(json.dumps(tamper, indent=2), encoding="utf-8")
    if _copy_tree(dirs.workspace / "runs", trace / "runs"):
        copied.append("runs")
    copied.extend(_copy_profiles(dirs.workspace, trace))
    if _copy_history(dirs.workspace, trace):
        copied.append("profile/history")
    copied.extend(_copy_proxy_audit(state_dir or dirs.state, trace))
    if _write_state(case.target.state_url, trace, problems):
        copied.append("target-state.json")
    for transcript in sorted(out.glob("transcript.*")):
        shutil.copy2(transcript, trace / transcript.name)
        copied.append(transcript.name)
    if not (trace / "runs").is_dir():
        problems.append("o agente nao gerou runs/: nada foi executado contra o alvo")
    manifest = {"copied": copied, "problems": problems, "tamper": tamper}
    (trace / "collect.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return CollectResult(trace, tuple(copied), tuple(problems))
