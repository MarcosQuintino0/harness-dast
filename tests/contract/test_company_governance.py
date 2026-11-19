"""Confere a cobertura do CODEOWNERS e o exemplo de configuração gerenciada."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PATTERNS = (
    "/docker/scope-proxy/",
    "/src/harness_dast/domain/scope*.py",
    "/src/harness_dast/domain/zap_scope.py",
    "/src/harness_dast/domain/pathpattern.py",
    "/src/harness_dast/adapters/scope_proxy/",
    "/src/harness_dast/application/scope_approval*.py",
    "/src/harness_dast/application/setup*.py",
    "/src/harness_dast/domain/setup_notes.py",
    "/src/harness_dast/adapters/storage/approval_store.py",
    "/src/harness_dast/cli/approval_*.py",
    "/src/harness_dast/cli/commands/profile.py",
    "/src/harness_dast/cli/commands/setup.py",
    "/src/harness_dast/cli/setup_composition.py",
    "/src/harness_dast/domain/letter*.py",
    "/src/harness_dast/domain/request_*.py",
    "/src/harness_dast/application/init_from_letter.py",
    "/src/harness_dast/adapters/storage/letter_reader.py",
    "/src/harness_dast/cli/commands/init.py",
    "/plugin/",
    "/.claude/settings.json",
    "/.claude-plugin/",
    "/.github/workflows/",
    "/AGENTS.md",
    "/CLAUDE.md",
    "/CODEOWNERS",
)


def matching_files(pattern: str) -> set[Path]:
    """Resolve o subconjunto usado aqui: caminhos da raiz e `*` no nome."""
    assert pattern.startswith("/"), f"Padrão precisa partir da raiz: {pattern}"
    assert not any(char in pattern for char in "?![]\\"), pattern
    assert "**" not in pattern, pattern
    assert "*" not in pattern.rsplit("/", 1)[0], pattern
    if pattern.endswith("/"):
        directory = ROOT / pattern.strip("/")
        return {path for path in directory.rglob("*") if path.is_file()}
    return {path for path in ROOT.glob(pattern[1:], case_sensitive=True) if path.is_file()}


def test_codeowners_patterns_match_files_and_cover_security_core() -> None:
    assert not (ROOT / ".github/CODEOWNERS").exists(), "O GitHub prioriza .github/CODEOWNERS."
    covered: set[Path] = set()
    for line in (ROOT / "CODEOWNERS").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        pattern, *owners = line.split()
        assert owners, f"Regra sem responsável: {line}"
        assert all(owner.startswith("@") for owner in owners), line
        matches = matching_files(pattern)
        assert matches, f"Nenhum arquivo encontrado para {pattern}"
        covered.update(matches)

    for pattern in CORE_PATTERNS:
        expected = matching_files(pattern)
        assert expected, f"O núcleo listado no teste mudou: {pattern}"
        missing = sorted(path.relative_to(ROOT).as_posix() for path in expected - covered)
        assert not missing, f"Arquivos do núcleo sem responsável: {missing}"


def test_managed_configuration_enables_only_the_company_marketplace() -> None:
    path = ROOT / "docs/empresa/configuracao-gerenciada.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    source = {"source": "git", "url": "https://gitlab.empresa.exemplo/qa/harness-dast.git"}

    assert settings == {
        "extraKnownMarketplaces": {"hdast": {"source": source}},
        "enabledPlugins": {"hdast@hdast": True},
        "strictKnownMarketplaces": [source],
    }
