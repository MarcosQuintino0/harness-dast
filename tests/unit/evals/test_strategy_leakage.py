"""A personalização não deve abrir um canal para pistas na cópia cega."""

from pathlib import Path

import pytest

from evals.runner.cases import EvalError
from evals.runner.prepare import prepare
from tests.unit.evals.support import CASES, make_round, write


def test_strategy_plans_and_qa_evidence_stay_out_of_blind_copy(repo: Path, out: Path) -> None:
    write(repo / "docs/plans/strategy.md", "segredo-do-gabarito")
    write(repo / "docs/reviews/strategy-qa.md", "segredo-do-gabarito")
    write(repo / "tests/unit/evals/test_strategy_example.py", "segredo-do-gabarito")
    write(repo / "products/private/strategy.yml", "segredo-do-gabarito")
    write(repo / "products/_template/strategy.yml", "schema_version: 1\n")

    dirs = make_round(repo, out)

    assert not (dirs.workspace / "docs/plans").exists()
    assert not (dirs.workspace / "docs/reviews").exists()
    assert not (dirs.workspace / "tests/unit/evals").exists()
    assert not (dirs.workspace / "products/private").exists()
    assert (dirs.workspace / "products/_template/strategy.yml").is_file()


def test_strategy_skill_with_answer_key_term_is_rejected(repo: Path, out: Path) -> None:
    write(repo / ".claude/skills/onboard-product/SKILL.md", "segredo-do-gabarito")

    with pytest.raises(EvalError, match="termo"):
        prepare("mini", "vulnerable", 1, out, source=repo, cases_dir=CASES)
