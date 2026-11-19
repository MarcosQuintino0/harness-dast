"""Layout `plugin` da copia cega: pasta de produtos para o agente e plugin fora dela.

Desenho do ADR 0119 (fase G). O workspace nao tem codigo da ferramenta: so o briefing, os insumos
do caso (`inputs/`), as pastas `products/`, `runs/` e `cartas/` e um `.claude/settings.json` so
com negacoes. O plugin vai para `<out>/plugin/` e o coordenador o carrega com
`claude --plugin-dir`; o `hdast` vem da instalacao do checkout dele (veja o guia do Codespaces).
"""

import json
import shutil
from dataclasses import replace
from pathlib import Path

from evals.runner import exclusions
from evals.runner.cases import RoundDirs
from evals.runner.leaks import LeakHit, scan_leaks

PRODUCT_FOLDERS = ("products", "runs", "cartas")
NOT_DELIVERED = (
    ("src", "codigo da CLI: o agente usa o hdast instalado fora do workspace"),
    ("docker", "recursos de build da pilha: ficam no checkout do coordenador"),
    ("lab", "laboratorio: o alvo foi construido por outra pessoa"),
    ("tests", "testes conhecem as falhas plantadas"),
    ("evals", "gabaritos, casos e o executor da avaliacao"),
    ("docs", "layout plugin: o guia vem das skills do plugin"),
)


def copy_plugin(source: Path, destination: Path) -> int:
    """Copia `plugin/` do checkout para `destination` e devolve quantos arquivos foram."""
    count = 0
    for file, rel in exclusions.walk_plugin(source / "plugin"):
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        count += 1
    return count


def add_product_folders(workspace: Path) -> None:
    """Cria as pastas onde o agente escreve (o hook do plugin limita as escritas a elas)."""
    for name in PRODUCT_FOLDERS:
        (workspace / name).mkdir(parents=True, exist_ok=True)


def write_settings(source: Path, workspace: Path, extra_deny: tuple[str, ...]) -> None:
    """Grava `.claude/settings.json` so com negacoes: as do repositorio e as da avaliacao.

    Sem `hooks` (o guard vale pelo `hooks.json` do plugin) e sem `allow` (o coordenador passa
    `--allowedTools` ao lancar o agente).
    """
    base = source / ".claude" / "settings.json"
    loaded = json.loads(base.read_text(encoding="utf-8")) if base.is_file() else {}
    inherited = loaded.get("permissions", {}).get("deny", [])
    deny = list(dict.fromkeys([*inherited, *extra_deny]))
    path = workspace / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"deny": deny}}, indent=2) + "\n", encoding="utf-8")


def write_manifest(dirs: RoundDirs, plugin_files: int) -> None:
    """Manifesto do preparo: o que o workspace tem e quantos arquivos o plugin levou."""
    counts: dict[str, int] = {}
    for file in sorted(dirs.workspace.rglob("*")):
        if file.is_file():
            root = file.relative_to(dirs.workspace).parts[0]
            counts[root] = counts.get(root, 0) + 1
    manifest = dirs.sealed / "workspace-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "policy": "products-folder-v1",
                "roots": dict(sorted(counts.items())),
                "total_files": sum(counts.values()),
                "stage": "products-folder",
                "plugin_files": plugin_files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def not_delivered(source: Path) -> list[str]:
    """Exclusoes que valeram no layout `plugin` (para `sealed/exclusions.json`)."""
    found = [f"{name}: {reason}" for name, reason in NOT_DELIVERED if (source / name).exists()]
    skills = source / "plugin" / "skills"
    if skills.is_dir():
        found.extend(
            f"plugin/skills/{entry.name}: skill fora da lista de uso"
            for entry in sorted(skills.iterdir())
            if entry.name not in exclusions.PLUGIN_SKILLS
        )
    return found


def scan_plugin_leaks(plugin: Path, terms: tuple[str, ...]) -> list[LeakHit]:
    """Termos do gabarito na copia do plugin, com o caminho prefixado por `plugin/`."""
    return [replace(hit, path=f"plugin/{hit.path}") for hit in scan_leaks(plugin, terms)]
