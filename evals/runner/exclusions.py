"""O que sai da copia entregue ao agente cego, e por que."""

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
    Exclusion("docs/reviews", "relatorios do laboratorio e de QA: dizem o que a V1 achou e perdeu"),
    Exclusion(
        "tests/fixtures/letter",
        "carta estruturada da Clinica Piloto: e o perfil esperado do caso, quase pronto",
    ),
    Exclusion("docs/spikes", "medicoes do spike sobre o ZAP e o alvo"),
    Exclusion("docs/plans", "planos e briefings do coordenador para a avaliacao"),
    Exclusion("docs/adr/0014-avaliacao-cega-como-eval.md", "desenho da avaliacao cega"),
    Exclusion("docs/guides/primeiro-uso.md", "aponta os perfis prontos do laboratorio"),
    Exclusion("reports", "pesquisa de projeto, fora da tarefa"),
    Exclusion("research_notes", "pesquisa de projeto, fora da tarefa"),
    Exclusion("lab/README.md", "lista as fraquezas documentadas do VAmPI e a ordem esperada"),
    Exclusion("lab/pilot/src", "codigo-fonte do alvo; blocos de falha marcados no codigo"),
    Exclusion("lab/pilot/Dockerfile", "como o alvo e construido (substituido por um stub)"),
    Exclusion("lab/pilot/pom.xml", "build do alvo"),
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
    return found
