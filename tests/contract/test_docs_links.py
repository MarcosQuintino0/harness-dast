"""Os links relativos dos documentos Markdown apontam para arquivo (e âncora) que existem.

Sem rede: links `http(s)://`, `mailto:` e afins são ignorados. Âncora segue a regra de títulos
do GitHub (minúsculas, sem pontuação, espaço vira hífen, repetição ganha `-1`, `-2`).
Blocos de código e trechos em crase não contam como link.
"""

import re
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
    "runs",
    "worktrees",
    "dist",
    "build",
    "translate-app",
    "sites",
}
LINK = re.compile(
    r"(?<!\\)!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
EXTERNAL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def markdown_files(root: Path) -> list[Path]:
    """Lista os `.md` do repositório, sem pastas geradas nem cópias de trabalho."""
    found: list[Path] = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts[:-1]):
            continue
        found.append(path)
    return sorted(found)


def slugify(title: str) -> str:
    """Âncora de um título, como o GitHub a calcula."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    text = text.replace("`", "").replace("*", "")
    text = unicodedata.normalize("NFC", text).strip().lower()
    kept = [c for c in text if c.isalnum() or c in " -_"]
    return "".join(kept).replace(" ", "-")


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Linhas fora de bloco de código, com o número da linha (a partir de 1)."""
    lines: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((number, line))
    return lines


def anchors_of(path: Path) -> set[str]:
    """Âncoras geradas pelos títulos do arquivo, mais `id=` escrito à mão."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for _, line in prose_lines(text):
        match = HEADING.match(line)
        if match is None:
            continue
        slug = slugify(match.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(re.findall(r"""(?:id|name)=["']([^"']+)["']""", text))
    return anchors


def broken_links(path: Path, root: Path) -> list[str]:
    """Descreve cada link relativo do arquivo que não leva a lugar nenhum."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for number, line in prose_lines(text):
        for match in LINK.finditer(CODE_SPAN.sub("", line)):
            target = match.group(1).strip("<>")
            if target == "" or EXTERNAL.match(target):
                continue
            file_part, _, anchor = target.partition("#")
            destination = path if file_part == "" else (path.parent / file_part.split("?")[0])
            where = f"{path.relative_to(root).as_posix()}:{number}"
            if not destination.exists():
                # O roteiro versionado gera a imagem de abertura depois da gravação.
                if (
                    path == root / "README.md"
                    and match.group(0).startswith("!")
                    and target == "docs/media/demo.gif"
                    and (root / "docs/media/demo.tape").is_file()
                ):
                    continue
                problems.append(f"{where}: arquivo não existe: {target}")
            elif (
                anchor
                and destination.suffix == ".md"
                and anchor.lower() not in anchors_of(destination)
            ):
                problems.append(f"{where}: âncora não existe: {target}")
    return problems


def test_markdown_links_point_to_existing_files_and_anchors() -> None:
    problems: list[str] = []
    for path in markdown_files(ROOT):
        problems.extend(broken_links(path, ROOT))
    assert problems == [], "links quebrados:\n" + "\n".join(problems)


def test_the_checker_finds_a_missing_file_and_a_missing_anchor(tmp_path: Path) -> None:
    (tmp_path / "alvo.md").write_text("# Título Um\n\n## Dois: e `três`\n", encoding="utf-8")
    (tmp_path / "origem.md").write_text(
        "[ok](alvo.md) [ok2](alvo.md#título-um) [ok3](alvo.md#dois-e-três) [self](#local)\n"
        "[falta](nada.md) [ancora](alvo.md#nao-existe) [web](https://x.test/a)\n"
        "`[código](nada2.md)`\n```\n[bloco](nada3.md)\n```\n\n# Local\n",
        encoding="utf-8",
    )

    problems = broken_links(tmp_path / "origem.md", tmp_path)

    assert [p.split(": ", 1)[1] for p in problems] == [
        "arquivo não existe: nada.md",
        "âncora não existe: alvo.md#nao-existe",
    ]


def test_the_checker_skips_generated_folders(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("x", encoding="utf-8")
    for folder in ("translate-app", "sites"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "outside.md").write_text("x", encoding="utf-8")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "b.md").write_text("x", encoding="utf-8")
    (tmp_path / ".claude" / "worktrees" / "w").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "w" / "c.md").write_text("x", encoding="utf-8")

    assert [p.name for p in markdown_files(tmp_path)] == ["a.md"]


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("M6: skills, documentação e avaliação cega", "m6-skills-documentação-e-avaliação-cega"),
        ("`hdast run` e `stop`", "hdast-run-e-stop"),
    ],
)
def test_slugify_follows_the_github_rule(title: str, slug: str) -> None:
    assert slugify(title) == slug


def test_readme_allows_only_the_generated_demo_image(tmp_path: Path) -> None:
    media = tmp_path / "docs" / "media"
    media.mkdir(parents=True)
    (media / "demo.tape").write_text("Output demo.gif\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "![hdast demo](docs/media/demo.gif)\n"
        "[download](docs/media/demo.gif)\n"
        "![outra imagem](docs/media/outra.gif)\n",
        encoding="utf-8",
    )

    assert broken_links(readme, tmp_path) == [
        "README.md:2: arquivo não existe: docs/media/demo.gif",
        "README.md:3: arquivo não existe: docs/media/outra.gif",
    ]
