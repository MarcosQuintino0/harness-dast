"""O exemplo do guia de autorização é uma carta estruturada válida e gera o perfil de ouro."""

import re
from pathlib import Path

import pytest

from harness_dast.adapters.storage.strict_yaml import parse_yaml_document
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter

pytestmark = pytest.mark.contract

ROOT = Path(__file__).parents[2]
GUIDE = ROOT / "docs" / "guides" / "modelo-de-autorizacao.md"
GOLDEN = ROOT / "tests" / "fixtures" / "letter" / "clinica-piloto.target.golden.yml"
_BLOCK = re.compile(r"```yaml\n(schema_version: 1\n.*?)```", re.DOTALL)


def _guide_letter() -> str:
    match = _BLOCK.search(GUIDE.read_text(encoding="utf-8"))
    assert match is not None, "o guia perdeu o exemplo de carta.yml"
    return match.group(1)


def test_guide_example_letter_is_ready_and_generates_the_golden_profile() -> None:
    letter = Letter.from_data(parse_yaml_document(_guide_letter(), "carta.yml"))

    review = review_letter(letter, "clinica-piloto")

    assert review.issues == ()
    assert review.profile_text == GOLDEN.read_text(encoding="utf-8")
