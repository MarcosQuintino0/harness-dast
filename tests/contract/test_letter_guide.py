"""O exemplo do guia de autorização é uma carta válida, gera o perfil de ouro e não vaza gabarito.

O exemplo é de um produto fictício (Livraria Exemplo), que não é nenhum caso de `evals/cases/`:
o guia vai na cópia entregue ao agente cego, e o perfil esperado de um caso não pode estar nele.
"""

import re
from pathlib import Path

import pytest

from evals.runner.cases import load_case
from evals.runner.exclusions import ALWAYS, decide
from evals.runner.leaks import scan_leaks
from harness_dast.adapters.storage.strict_yaml import parse_yaml_document
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter

pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]
GUIDE = ROOT / "docs" / "guides" / "modelo-de-autorizacao.md"
FIXTURES = ROOT / "tests" / "fixtures" / "letter"
GOLDEN = FIXTURES / "livraria-exemplo.target.golden.yml"
CASES = ROOT / "evals" / "cases"
_BLOCK = re.compile(r"```yaml\n(schema_version: 1\n.*?)```", re.DOTALL)


def _guide_letter() -> str:
    match = _BLOCK.search(GUIDE.read_text(encoding="utf-8"))
    assert match is not None, "o guia perdeu o exemplo de carta.yml"
    return match.group(1)


def test_guide_example_letter_is_ready_and_generates_the_golden_profile() -> None:
    letter = Letter.from_data(parse_yaml_document(_guide_letter(), "carta.yml"))

    review = review_letter(letter, "livraria-exemplo")

    assert review.issues == ()
    assert review.profile_text == GOLDEN.read_text(encoding="utf-8")


def test_guide_example_letter_is_the_livraria_fixture() -> None:
    fixture = (FIXTURES / "livraria-exemplo.carta.yml").read_text(encoding="utf-8")

    assert _guide_letter() == fixture


def _answer_terms(case_name: str) -> tuple[str, ...]:
    """Termos que identificam o perfil esperado de um caso (o que o agente cego deve descobrir)."""
    case = load_case(case_name, CASES)
    expected = case.expected
    terms = {*case.leak_terms, expected.reference, expected.base_url, *expected.deny_paths}
    for rule in expected.allow:
        terms.update(path for path in rule.paths if len(path) > 1)
    for account in expected.accounts:
        terms.update((account.alias, account.username_env, account.password_env))
    return tuple(sorted(terms))


def _delivered_text_files() -> list[Path]:
    """Guias, skills e subagentes que ficam na cópia entregue ao agente cego."""
    found = [
        *sorted((ROOT / "docs" / "guides").glob("*.md")),
        *sorted((ROOT / ".claude").glob("**/*.md")),
        ROOT / "README.md",
    ]
    return [path for path in found if decide(path.relative_to(ROOT).as_posix(), ALWAYS) is None]


def test_delivered_guides_and_skills_do_not_contain_the_expected_profile_of_any_case(
    tmp_path: Path,
) -> None:
    delivered = _delivered_text_files()
    assert GUIDE in delivered
    for path in delivered:
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    cases = sorted(entry.name for entry in CASES.iterdir() if entry.is_dir())

    leaks = [
        f"{case}: {hit.path} linha {hit.line}: {hit.term}"
        for case in cases
        for hit in scan_leaks(tmp_path, _answer_terms(case))
    ]

    assert not leaks, "\n".join(leaks)
