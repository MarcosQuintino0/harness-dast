"""`prepare`: cria o workspace cego, lacra o modo e escreve o briefing."""

import json
import random
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from evals.runner import exclusions, gitutil
from evals.runner.briefing import build_briefing
from evals.runner.cases import (
    CASES_DIR,
    REPO_ROOT,
    EvalError,
    RoundDirs,
    load_case,
    read_authorization,
)
from evals.runner.leaks import LeakHit, scan_leaks
from evals.runner.models import Case

MODES = ("vulnerable", "secure", "random")
BRIEFING_NAME = "EVAL-BRIEFING.md"


@dataclass(frozen=True)
class PrepareResult:
    """O que o `prepare` devolve (o modo sorteado nunca vai para a tela)."""

    workspace: Path
    sealed: Path
    excluded: tuple[str, ...]
    leaks: tuple[LeakHit, ...]


def resolve_mode(case: Case, requested: str, seed: int) -> str:
    """Resolve `random` com a semente; recusa modo que o caso nao tem.

    Raises:
        EvalError: Modo desconhecido ou nao suportado pelo caso.
    """
    if requested not in MODES:
        raise EvalError(f"Modo '{requested}' invalido. Use vulnerable, secure ou random.")
    if requested == "random":
        return random.Random(seed).choice(case.modes)  # noqa: S311 - sorteio reprodutivel, nao e criptografia
    if requested not in case.modes:
        raise EvalError(f"O caso {case.name} nao tem o modo {requested}.")
    return requested


def draw_secrets(case: Case) -> dict[str, str]:
    """Segredos da rodada: os fixos do laboratorio e os sorteados (so o sorteado e sigiloso)."""
    values = dict(case.secrets.fixed)
    for name in case.secrets.generate:
        if name.endswith("EMAIL"):
            values[name] = f"lab.{secrets.token_hex(4)}@example.com"
        elif name.endswith(("USERNAME", "USER")):
            values[name] = "lab_" + secrets.token_hex(8)
        else:
            values[name] = case.secrets.password_prefix + secrets.token_hex(16)
    return values


def copy_workspace(case: Case, source: Path, workspace: Path) -> list[str]:
    """Copia o repositorio sem o que o agente nao pode ver. Devolve as exclusoes que valeram."""
    rules = exclusions.exclusions_for(case)
    for file, rel in exclusions.walk_kept(source, rules):
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    return [f"{rule.path}: {rule.reason}" for rule in exclusions.applied(source, rules)]


def deliver_inputs(case: Case, source: Path, workspace: Path) -> None:
    """Coloca no workspace o que o dono do produto entrega (OpenAPI) e os arquivos de apoio."""
    for item in case.deliver:
        origin = source / item.source
        if not origin.is_file():
            raise EvalError(f"Arquivo a entregar nao existe: {item.source}.")
        target = workspace / item.dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    for rel, content in case.write_files.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (workspace / "products").mkdir(exist_ok=True)


EXTRA_DENY = (
    "Bash(docker:*)",
    "Bash(docker-compose:*)",
    "Bash(env:*)",
    "Bash(set:*)",
    "PowerShell(docker:*)",
    "PowerShell(docker-compose:*)",
    "PowerShell(Get-ChildItem env:*)",
    "PowerShell(Get-Item env:*)",
    "PowerShell(gci env:*)",
    "Read(//**/state/**)",
    "Read(//**/sealed/**)",
    # Aprovacao humana do escopo (ADR 0037): o agente nao aprova, nao grava na pasta de estado
    # (onde mora a aprovacao) nem chama o executor da avaliacao que aprova pelo coordenador.
    "Bash(uv run hdast profile approve:*)",
    "Bash(uv run hdast --json profile approve:*)",
    "Bash(hdast profile approve:*)",
    "Bash(hdast --json profile approve:*)",
    "PowerShell(uv run hdast profile approve:*)",
    "PowerShell(uv run hdast --json profile approve:*)",
    "PowerShell(hdast profile approve:*)",
    "PowerShell(hdast --json profile approve:*)",
    "Bash(uv run python -m evals.runner:*)",
    "Bash(python -m evals.runner:*)",
    "PowerShell(uv run python -m evals.runner:*)",
    "PowerShell(python -m evals.runner:*)",
    "Edit(//**/state/**)",
    "Write(//**/state/**)",
)
"""Permissoes negadas so no workspace: fecham canais pelos quais o agente descobriria o modo
(`docker inspect`, `env`), leria o estado da pilha ou aprovaria o proprio escopo. Nao mudam o
repositorio original."""


def harden_settings(workspace: Path) -> None:
    """Acrescenta `EXTRA_DENY` ao `.claude/settings.json` da copia (antes da base do git)."""
    path = workspace / ".claude" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    deny.extend(rule for rule in EXTRA_DENY if rule not in deny)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def write_sealed(
    case: Case, dirs: RoundDirs, mode: str, requested: str, seed: int, values: dict[str, str]
) -> None:
    """Grava o lacre: modo, segredos e o ambiente que o coordenador aplica ao processo do agente."""
    dirs.sealed.mkdir(parents=True, exist_ok=True)
    (dirs.sealed / "mode.json").write_text(
        json.dumps(
            {"case": case.name, "mode": mode, "requested": requested, "seed": seed}, indent=2
        ),
        encoding="utf-8",
    )
    (dirs.sealed / "case.json").write_text(case.model_dump_json(indent=2), encoding="utf-8")
    (dirs.sealed / "secrets.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
    mode_env = {case.target.mode.env_var: case.target.mode.values[mode]} if case.target.mode else {}
    env = {
        **values,
        **mode_env,
        "HDAST_PRODUCTS_DIR": str((dirs.workspace / "products").resolve()),
        "HDAST_STATE_DIR": str(dirs.state.resolve()),
    }
    (dirs.sealed / "agent-env.json").write_text(json.dumps(env, indent=2), encoding="utf-8")


def prepare(
    case_name: str,
    mode: str,
    seed: int,
    out: Path,
    *,
    source: Path = REPO_ROOT,
    allow_leaks: bool = False,
    cases_dir: Path = CASES_DIR,
) -> PrepareResult:
    """Cria `<out>/workspace` e `<out>/sealed`.

    Raises:
        EvalError: Pasta de saida nao vazia, caso invalido, git ausente ou termo do gabarito.
    """
    case = load_case(case_name, cases_dir)
    dirs = RoundDirs(out)
    if out.exists() and any(out.iterdir()):
        raise EvalError(f"{out} nao esta vazia: use uma pasta nova para cada rodada.")
    resolved = resolve_mode(case, mode, seed)
    excluded = copy_workspace(case, source, dirs.workspace)
    deliver_inputs(case, source, dirs.workspace)
    harden_settings(dirs.workspace)
    briefing = build_briefing(case, read_authorization(case_name, case, cases_dir))
    (dirs.workspace / BRIEFING_NAME).write_text(briefing, encoding="utf-8")
    leaks = tuple(scan_leaks(dirs.workspace, case.leak_terms))
    write_sealed(case, dirs, resolved, mode, seed, draw_secrets(case))
    (dirs.sealed / "exclusions.json").write_text(json.dumps(excluded, indent=2), encoding="utf-8")
    (dirs.sealed / "leak-report.json").write_text(
        json.dumps([hit.__dict__ for hit in leaks], indent=2), encoding="utf-8"
    )
    dirs.state.mkdir(parents=True, exist_ok=True)
    if leaks and not allow_leaks:
        raise EvalError(
            f"{len(leaks)} termo(s) do gabarito na copia "
            f"(veja {dirs.sealed / 'leak-report.json'}). "
            "Acrescente o caminho em `exclude` do case.yml ou use --allow-leaks conscientemente."
        )
    gitutil.init_baseline(dirs.workspace)
    return PrepareResult(dirs.workspace, dirs.sealed, tuple(excluded), leaks)
