"""QA independente: a documentação descreve o que o código faz?

Três verificações: (1) toda flag e todo subcomando `hdast` citado nos documentos existe e toda
flag real está documentada em `docs/referencia/`; (2) a tabela de códigos de saída bate com
`ExitCode`; (3) frases que dão como inexistente ou planejado algo que já foi entregue (lista
explícita, verificada contra o código). Um teste de (3) falha enquanto a frase velha continuar
no documento.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import typer.main

from harness_dast.cli.app import build_app
from harness_dast.domain.errors import ExitCode

ROOT = Path(__file__).resolve().parents[2]
DOC_FILES = [
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "AGENTS.md",
    *sorted((ROOT / "docs" / "referencia").glob("*.md")),
    *sorted((ROOT / "docs" / "como-funciona" / "operacao").glob("*.md")),
    *sorted((ROOT / "docs" / "desenvolver" / "modulos").glob("*.md")),
    ROOT / "docs" / "como-funciona" / "arquitetura.md",
    ROOT / "docs" / "desenvolver" / "testing.md",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _walk(command: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    # O typer pode trazer o próprio click; por isso a checagem é por atributo, não por tipo.
    found = [(prefix, command)]
    for name, sub in getattr(command, "commands", {}).items():
        found.extend(_walk(sub, (*prefix, name)))
    return found


def _real_commands() -> dict[tuple[str, ...], Any]:
    root = typer.main.get_command(build_app())
    return {path: cmd for path, cmd in _walk(root) if path}


def _real_flags() -> set[str]:
    flags: set[str] = {"--json", "--help"}
    for cmd in _real_commands().values():
        for param in cmd.params:
            flags.update(opt for opt in param.opts if opt.startswith("--"))
            flags.update(opt for opt in param.secondary_opts if opt.startswith("--"))
    return flags


# ----------------------------------------------------------------------- flags e comandos


def test_every_flag_shown_on_an_hdast_line_exists_in_the_cli() -> None:
    real = _real_flags()
    missing: list[str] = []
    for path in DOC_FILES:
        for number, line in enumerate(_text(path).splitlines(), start=1):
            if "hdast " not in line or "docker" in line or "uv run pytest" in line:
                continue
            for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]+", line):
                if flag not in real:
                    missing.append(f"{path.relative_to(ROOT)}:{number}: {flag}")

    assert not missing, "\n".join(missing)


def test_every_real_flag_is_documented_somewhere_in_docs_reference() -> None:
    corpus = "\n".join(_text(path) for path in (ROOT / "docs" / "referencia").glob("*.md"))
    undocumented = sorted(flag for flag in _real_flags() if flag not in corpus)

    assert not undocumented, undocumented


def test_every_subcommand_cited_after_hdast_exists() -> None:
    real_first = {path[0] for path in _real_commands()}
    real_pairs = {" ".join(path) for path in _real_commands() if len(path) == 2}
    groups = {path[0] for path in _real_commands() if len(path) == 2}
    unknown: list[str] = []
    for path in DOC_FILES:
        for number, line in enumerate(_text(path).splitlines(), start=1):
            for match in re.finditer(
                r"(?<![\w/.-])hdast (?:--json )?([a-z][a-z-]*)(?: ([a-z][a-z-]*))?", line
            ):
                first, second = match.group(1), match.group(2)
                if first in {
                    "e",
                    "ou",
                    "de",
                    "do",
                    "da",
                    "que",
                    "usa",
                    "em",
                    "a",
                    "o",
                    "para",
                    "é",
                }:
                    continue
                if first not in real_first:
                    unknown.append(f"{path.relative_to(ROOT)}:{number}: hdast {first}")
                elif first in groups and second and f"{first} {second}" not in real_pairs:
                    if second in {"up", "down", "status", "validate", "inspect"}:
                        continue
                    unknown.append(f"{path.relative_to(ROOT)}:{number}: hdast {first} {second}")

    assert not unknown, "\n".join(unknown)


# ----------------------------------------------------------------------- códigos de saída


def test_exit_code_table_matches_the_enum() -> None:
    table = _text(ROOT / "docs" / "referencia" / "exit-codes.md")
    rows = re.findall(r"^\| `(\d+)` \| (.+?) \|", table, flags=re.MULTILINE)
    documented = {int(code): name.strip("` ") for code, name in rows}
    expected = {int(item): item.name for item in ExitCode}

    assert set(documented) == set(expected)
    for code, name in documented.items():
        if not name.startswith("("):
            assert name == expected[code]


def test_error_code_table_in_cli_reference_lists_the_exit_code_of_each_error() -> None:
    from harness_dast.domain import errors

    text = _text(ROOT / "docs" / "referencia" / "cli.md")
    section = text.split("## Valores de `error.code`", 1)[1]
    rows = dict(re.findall(r"^\| `([A-Z_]+)` \|.*\| (\d+) \|$", section, flags=re.MULTILINE))
    classes = [
        cls
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, errors.HarnessError)
    ]
    wrong = [
        f"{cls.code}: doc {rows[cls.code]} != código {int(cls.exit_code)}"
        for cls in classes
        if cls.code in rows and rows[cls.code] != str(int(cls.exit_code))
    ]

    assert not wrong, wrong


def test_every_hdast_environment_variable_read_by_the_code_is_documented() -> None:
    documented = _text(ROOT / "docs" / "referencia" / "env-vars.md")
    sources = [
        ROOT / "src" / "harness_dast" / "application" / "stack.py",
        ROOT / "src" / "harness_dast" / "adapters" / "storage" / "stack_state.py",
        ROOT / "src" / "harness_dast" / "config" / "settings.py",
    ]
    used: set[str] = set()
    for source in sources:
        used.update(re.findall(r'"(HDAST_[A-Z_]+)"', _text(source)))
    used.discard("HDAST_LIMPEZA")

    missing = sorted(name for name in used if name not in documented)

    assert not missing, missing


# ------------------------------------------------- frases velhas sobre o que já foi entregue

STALE = [
    (
        "docs/referencia/cli.md",
        "`CLEANUP_FAILED` ainda não é alcançado por nenhum comando",
        "`hdast cleanup` existe e sai com 7 (CLEANUP_FAILED)",
    ),
    (
        "docs/referencia/cli.md",
        "o cenário de escopo ainda não existe em código",
        "o ScopeGuard é chamado por preflight, probe e scan",
    ),
    (
        "docs/referencia/data-rules-yml.md",
        "**Não existe** comando `hdast` que leia este arquivo",
        "`hdast probe` e `scan` leem data-rules.yml",
    ),
    (
        "docs/referencia/flows-yml.md",
        "**Não existe** comando `hdast` que leia este arquivo",
        "`hdast probe` lê flows.yml",
    ),
    (
        "products/_template/README.md",
        "ainda **não existem** (são planejados)",
        "`hdast init` e `profile validate` existem desde o M2",
    ),
    (
        "docs/desenvolver/modulos/config.md",
        "**Planejado** (segunda metade do M2); não existe",
        "o carregador de perfil existe em adapters/storage/profile_repository.py",
    ),
    (
        "docs/desenvolver/modulos/observability.md",
        "componente de origem | Planejado, M3 |",
        "audit.jsonl existe desde o M3",
    ),
    (
        "docs/como-funciona/operacao/authorization-and-scope.md",
        "| 2. ZAP em modo protegido | Contexto do ZAP restrito aos mesmos hosts e caminhos "
        "| Planejado (M4) |",
        "o contexto por execução existe desde o M4",
    ),
    (
        "docs/desenvolver/testing.md",
        "são planejados a partir do M3 e M4; não existem hoje",
        "tests/integration/ existe e roda contra o lab",
    ),
    (
        "docs/desenvolver/modulos/domain.md",
        "| `finding.py` | `Finding`, `Evidence`, `Severity`, `Fingerprint` | M4 |",
        "domain/finding.py existe",
    ),
]


@pytest.mark.parametrize(
    ("relative", "phrase", "reality"), STALE, ids=[f"stale-{index}" for index in range(len(STALE))]
)
def test_documents_do_not_call_a_delivered_feature_missing_or_planned(
    relative: str, phrase: str, reality: str
) -> None:
    assert phrase not in _text(ROOT / relative), f"documento velho; realidade: {reality}"
