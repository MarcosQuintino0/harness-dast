"""O exemplo do guia de autorização é uma carta válida, gera o perfil de ouro e não vaza gabarito.

O exemplo é de um produto fictício (Livraria Exemplo), que não é nenhum caso de `evals/cases/`:
o guia vai na cópia entregue ao agente cego, e o perfil esperado de um caso não pode estar nele.
"""

import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from evals.runner.cases import load_case
from evals.runner.exclusions import exclusions_for, walk_kept
from evals.runner.leaks import MAX_BYTES, scan_leaks
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

    review = review_letter(letter, "livraria-exemplo", date(2026, 11, 14))

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


def _secret_terms(case_name: str) -> tuple[str, ...]:
    """O que só o dono do produto sabe: caminhos proibidos, a isca e as falhas plantadas.

    Termos genéricos do caso (`/api/**`, apelidos de conta, variáveis do laboratório) existem de
    propósito no código e nos testes do repositório e não entram aqui; a busca nos guias e nas
    skills, com a lista completa, é o teste acima.
    """
    case = load_case(case_name, CASES)
    terms = {*case.leak_terms, *case.expected.deny_paths, *case.forbidden.zero_counters}
    terms.update(prefix for prefix in case.forbidden.path_prefixes if len(prefix) > 1)
    return tuple(sorted(terms))


def _copy_delivered(case_name: str, destination: Path) -> int:
    """Copia, para `destination`, todo arquivo que o `evals/runner` entregaria ao agente cego.

    A decisão de o que sai é a do próprio executor (`exclusions_for` e `walk_kept`): nenhuma
    regra é repetida aqui. Devolve quantos arquivos foram copiados.
    """
    case = load_case(case_name, CASES)
    copied = 0
    for file, rel in walk_kept(ROOT, exclusions_for(case)):
        if file.stat().st_size > MAX_BYTES:
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        copied += 1
    return copied


CASE_NAMES = sorted(entry.name for entry in CASES.iterdir() if entry.is_dir())


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_the_copy_delivered_to_the_blind_agent_has_no_answer_of_the_case(
    case_name: str, tmp_path: Path
) -> None:
    """Nenhum arquivo da cópia cega (guias, skills, docs, código, testes) traz o gabarito do caso.

    Vale para todo arquivo que o executor entrega, não só guias e skills: um exemplo de `docs/`
    com o caminho proibido ou a isca do caso entrega a resposta.
    """
    assert _copy_delivered(case_name, tmp_path) > 0
    assert (tmp_path / "docs" / "guides" / GUIDE.name).exists()

    leaks = [
        f"{hit.path} linha {hit.line}: {hit.term}"
        for hit in scan_leaks(tmp_path, _secret_terms(case_name))
    ]

    assert not leaks, case_name + ":\n" + "\n".join(leaks)
