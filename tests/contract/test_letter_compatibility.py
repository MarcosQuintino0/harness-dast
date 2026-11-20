"""Contrato histórico do YAML e da impressão digital das cartas versionadas."""

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from harness_dast.adapters.storage.letter_reader import FileLetterReader
from harness_dast.adapters.storage.strict_yaml import parse_yaml_document
from harness_dast.domain.letter import Letter
from harness_dast.domain.letter_review import review_letter
from harness_dast.domain.profile import ProductProfile
from harness_dast.domain.scope_fingerprint import block_digests, combine_digests

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]
REVIEW_DATE = date(2026, 11, 18)


@pytest.mark.parametrize(
    ("relative_path", "expected_yaml", "expected_fingerprint"),
    # SHA-256 do texto UTF-8 (incluindo comentários) e impressão digital na base fffef79b.
    [
        (
            "tests/fixtures/letter/clinica-piloto.carta.yml",
            "88a0e50816cb8455075c1fa111700587f3f4b90c72d697bb6c220e5852f5a0b0",
            "93430c788793ce89c6df74bcb63673626c488899e8318eeee6d2a4c3737d76cb",
        ),
        (
            "tests/fixtures/letter/livraria-exemplo.carta.yml",
            "399802410fd256e1a228564c6ced531d9aa1cf57f2c3f6ff30ad4a70770ca197",
            "e08a67ec82f7062a3992536ec817dcc5858e5a6daf193cc087d2784a7f6a32a6",
        ),
        (
            "evals/cases/crapi-foco/carta.yml",
            "574c3a317cd814fd50a8472e74a2edf99124c63177007ef631ebc98b35d3f542",
            "7d0a26b23e6dc327f60e1faaf583395b6bd84ff343897af330326f5fd643b428",
        ),
    ],
    ids=("clinica-piloto", "livraria-exemplo", "crapi-foco"),
)
def test_geracao_preserva_yaml_e_impressao_digital_quando_a_carta_e_historica(
    relative_path: str, expected_yaml: str, expected_fingerprint: str
) -> None:
    letter = Letter.from_data(FileLetterReader().read(ROOT / relative_path))

    result = review_letter(letter, letter.product, REVIEW_DATE)

    assert result.profile_text is not None, result.issues
    assert sha256(result.profile_text.encode("utf-8")).hexdigest() == expected_yaml
    profile = ProductProfile.from_data(parse_yaml_document(result.profile_text, "target.yml"))
    assert combine_digests(profile.product, block_digests(profile)) == expected_fingerprint
