"""Fronteira da cópia cega: raízes permitidas e exclusões finas internas."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from evals.runner.models import Case

SEALED_LAB = "o alvo foi construido por outra pessoa; o agente nao ve como"


@dataclass(frozen=True)
class Exclusion:
    """Um caminho (relativo a raiz, com barras normais) retirado da copia."""

    path: str
    reason: str


ALWAYS: tuple[Exclusion, ...] = (
    Exclusion(
        ".git", "historico do repositorio (mensagens de commit revelam o desenho da avaliacao)"
    ),
    Exclusion(".venv", "ambiente do coordenador"),
    Exclusion("runs", "execucoes anteriores: dizem o que a ferramenta achou"),
    Exclusion(".env", "segredos do coordenador"),
    Exclusion(".claude/settings.local.json", "permissoes locais do coordenador"),
    Exclusion(
        ".claude/worktrees",
        "copias de trabalho de outros agentes: trazem gabaritos e perfis",
    ),
    Exclusion("coverage.xml", "artefato de teste"),
    Exclusion(".coverage", "artefato de teste"),
    Exclusion("evals", "gabaritos, casos e o proprio executor da avaliacao"),
    Exclusion("tests/unit/evals", "testes do executor: descrevem as falhas plantadas"),
    Exclusion(
        "tests/integration", "testes que conhecem as falhas plantadas e o resultado esperado"
    ),
    Exclusion("docs/arquivo", "histórico de laboratório, QA, planos, pesquisas e desenhos"),
    Exclusion(
        "tests/fixtures/letter",
        "carta estruturada da Clinica Piloto: e o perfil esperado do caso, quase pronto",
    ),
    Exclusion("docs/decisoes/0014-avaliacao-cega-como-eval.md", "desenho da avaliacao cega"),
    Exclusion("docs/comecar/primeiro-uso.md", "aponta os perfis prontos do laboratorio"),
    Exclusion("CHANGELOG.md", "histórico com resultados do laboratório"),
    Exclusion("docs/roadmap.md", "estado com resultados e lacunas do laboratório"),
    Exclusion("docs/decisoes/0083-copia-cega-por-lista-de-permissao.md", "fronteira da avaliação"),
    Exclusion("docs/referencia/verification-calibration.md", "calibracao privada"),
    Exclusion("docs/referencia/verification-calibration.json", "calibracao privada"),
    Exclusion(
        "docs/decisoes/0088-apresentacao-e-calibracao-de-verificacao.md", "calibracao privada"
    ),
    Exclusion("docs/decisoes/0089-criterio-privado-triagem.md", "critério privado da avaliação"),
    Exclusion("lab/README.md", "lista as fraquezas documentadas do VAmPI e a ordem esperada"),
    Exclusion("lab/pilot/src", "codigo-fonte do alvo; blocos de falha marcados no codigo"),
    Exclusion("lab/pilot/Dockerfile", "como o alvo e construido (substituido por um stub)"),
    Exclusion("lab/pilot/pom.xml", "build do alvo"),
    Exclusion(
        "lab/pilot/target",
        "saida de build do alvo (ignorada pelo git): classes compiladas revelam o codigo",
    ),
    Exclusion("lab/pilot/README.md", "descreve o alvo por dentro"),
    Exclusion("lab/pilot/.env", "senhas do alvo"),
    Exclusion("lab/pilot/.env.example", "variaveis internas do alvo"),
    Exclusion("lab/pilot/.dockerignore", "build do alvo"),
    Exclusion("lab/pilot/.gitignore", "build do alvo"),
    Exclusion("lab/pilot/scripts", "scripts do alvo"),
    Exclusion("lab/pilot/documentos", "arquivos servidos pelo alvo"),
    Exclusion("lab/pilot/cleanup", "script de limpeza: autoria humana, nao faz parte da prova"),
    Exclusion("lab/pilot/openapi.json", "entregue em inputs/ pelo dono do produto"),
    Exclusion("lab/pilot/product-profile", "perfil pronto: escrever o perfil e parte da prova"),
    Exclusion("lab/vampi/product-profile", "perfil pronto: escrever o perfil e parte da prova"),
    Exclusion("lab/vampi/openapi3.yml", "entregue em inputs/ pelo dono do produto"),
    Exclusion("lab/crapi/product-profile", "perfil pronto: escrever o perfil e parte da prova"),
    Exclusion("lab/crapi/openapi.json", "entregue em inputs/ pelo dono do produto"),
)

# Testes não são necessários para operar a CLI e contêm expectativas e fixtures do laboratório.
# Raiz nova exige decisão explícita; arquivos necessários ao build/template e à pilha permanecem.
ALLOWED_ROOTS = (
    "src",
    "docker",
    "compose.yaml",
    "lab",
    "products/_template",
    ".claude",
    "docs",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".gitattributes",
    ".gitignore",
    ".dockerignore",
    ".env.example",
)


CACHE_NAMES = frozenset(
    {"__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".hypothesis", "node_modules"}
)
KEPT_PRODUCT = "_template"


def exclusions_for(case: Case) -> tuple[Exclusion, ...]:
    """Exclusoes fixas mais as do caso."""
    extra = tuple(Exclusion(path, "exclusao do caso") for path in case.exclude)
    return (*ALWAYS, *extra)


def _matches(rel: str, rules: tuple[Exclusion, ...]) -> Exclusion | None:
    for rule in rules:
        if rel == rule.path or rel.startswith(rule.path + "/"):
            return rule
    return None


def _product_exclusion(rel: str) -> Exclusion | None:
    parts = rel.split("/")
    if len(parts) == 2 and parts[0] == "products" and parts[1] != KEPT_PRODUCT:
        return Exclusion(rel, "perfil real do coordenador")
    return None


def decide(rel: str, rules: tuple[Exclusion, ...]) -> Exclusion | None:
    """Diz se o caminho relativo sai da copia e por que."""
    if rel.split("/")[-1] in CACHE_NAMES:
        return Exclusion(rel, "cache")
    parts = rel.split("/")
    if parts[-1] == ".env" or (parts[-1].startswith(".env.") and parts[-1] != ".env.example"):
        return Exclusion(rel, "arquivo local de segredos")
    if len(parts) >= 3 and parts[:2] == [".claude", "skills"] and parts[2].startswith("dev-"):
        return Exclusion(rel, "skill de desenvolvimento, fora da tarefa operacional")
    if not any(
        rel == path or rel.startswith(path + "/") or path.startswith(rel + "/")
        for path in ALLOWED_ROOTS
    ):
        return Exclusion(rel, "fora da lista de permissão de raízes")
    return _matches(rel, rules) or _product_exclusion(rel)


def walk_kept(root: Path, rules: tuple[Exclusion, ...]) -> Iterator[tuple[Path, str]]:
    """Gera (arquivo, caminho relativo) de tudo que fica; poda as pastas excluidas."""
    stack = [root]
    while stack:
        folder = stack.pop()
        for entry in sorted(folder.iterdir()):
            rel = entry.relative_to(root).as_posix()
            if decide(rel, rules) is not None:
                continue
            if entry.is_symlink():
                continue
            if entry.is_dir():
                stack.append(entry)
            elif entry.is_file():
                yield entry, rel


def applied(root: Path, rules: tuple[Exclusion, ...]) -> list[Exclusion]:
    """Regras que de fato retiraram algo (o caminho existe na origem)."""
    found = [rule for rule in rules if (root / rule.path).exists()]
    products = root / "products"
    if products.is_dir():
        for entry in sorted(products.iterdir()):
            hit = _product_exclusion(entry.relative_to(root).as_posix())
            if hit is not None:
                found.append(hit)
    for entry in sorted(root.iterdir()):
        hit = decide(entry.name, rules)
        if hit is not None and hit not in found:
            found.append(hit)
    skills = root / ".claude" / "skills"
    if skills.is_dir():
        found.extend(
            Exclusion(p.relative_to(root).as_posix(), "skill de desenvolvimento")
            for p in sorted(skills.glob("dev-*"))
        )
    return found
