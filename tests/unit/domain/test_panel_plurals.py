"""Concordância de número nas frases geradas: nada de "1 funções" nem "apareceu 3 falhas"."""

import re

import pytest

from harness_dast.domain.panel_build_content import build_steps
from harness_dast.domain.panel_format import pick, plural
from harness_dast.domain.panel_model import PanelFunction, PanelView
from harness_dast.domain.panel_pages import render_panel
from harness_dast.domain.run_summary import StageRecord
from tests.unit.domain.panel_helpers import run_summary, view

BAD = re.compile(r"\b1 (funções|falhas|motivos|regras|testes|pedidos|achados|causas|etapas)\b")


def main_text(page: str) -> str:
    body = re.search(r"<main.*?</main>", page, re.S).group(0)  # type: ignore[union-attr]
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def function(state: str, index: int = 0) -> PanelFunction:
    return PanelFunction(
        operation_id=f"op{state}{index}",
        method="GET",
        path="/p",
        name="f",
        area="x",
        state=state,  # type: ignore[arg-type]  # parametrização do teste
    )


@pytest.mark.parametrize(
    ("value", "expected"), [(0, "foram"), (1, "foi"), (2, "foram"), (30, "foram")]
)
def test_pick_chooses_the_singular_only_for_one(value: int, expected: str) -> None:
    assert pick(value, "foi", "foram") == expected


def test_plural_keeps_the_number_with_the_right_word() -> None:
    assert plural(1, "motivo", "motivos") == "1 motivo"
    assert plural(2, "motivo", "motivos") == "2 motivos"


def test_the_steps_agree_with_one_forbidden_and_one_unanswered_function() -> None:
    steps = build_steps(
        severe=(),
        counts=None,
        functions=(function("forbidden"), function("failed")),
        authz=None,
        partial=False,
    )
    text = " ".join(item.text for item in steps)

    assert "Conferir se a função proibida pela carta deve mesmo ficar de fora" in text
    assert "melhorar o alcance da função que não respondeu" in text
    assert not BAD.search(text)


def test_the_steps_agree_with_many_functions() -> None:
    steps = build_steps(
        severe=(),
        counts=None,
        functions=(
            function("forbidden", 0),
            function("forbidden", 1),
            function("failed", 0),
            function("failed", 1),
        ),
        authz=None,
        partial=False,
    )
    text = " ".join(item.text for item in steps)

    assert "as 2 funções proibidas pela carta devem mesmo ficar de fora" in text
    assert "melhorar o alcance das 2 funções que não responderam" in text


def partial_view(severe_count: int) -> PanelView:
    summary = run_summary(
        status="failed",
        stages=(
            StageRecord(name="preflight", status="ok"),
            StageRecord(name="probe", status="ok"),
            StageRecord(name="scan", status="failed", message="acabou o tempo"),
            StageRecord(name="authz", status="not_run"),
            StageRecord(name="report", status="not_run"),
        ),
    )
    base = view(summary=summary)
    verdict = base.verdict.model_copy(update={"severe_count": severe_count})
    return base.model_copy(update={"verdict": verdict})


@pytest.mark.parametrize(
    ("count", "phrase"),
    [(1, "Até ali apareceu 1 falha grave"), (3, "Até ali apareceram 3 falhas graves")],
)
def test_the_partial_summary_makes_the_verb_agree_with_the_severe_count(
    count: int, phrase: str
) -> None:
    text = main_text(render_panel(partial_view(count))["summary.html"])

    assert phrase in text


def test_the_summary_says_one_group_not_several() -> None:
    base = view()
    counts = base.counts.model_copy(update={"groups": 1, "low": 4})  # type: ignore[union-attr]
    text = main_text(render_panel(base.model_copy(update={"counts": counts}))["summary.html"])

    assert "agrupado em 1 causa" in text
    assert "agrupados em 1 causa" not in text


def test_no_page_of_the_happy_view_has_a_one_with_a_plural_noun() -> None:
    for name, page in render_panel(view()).items():
        assert not BAD.search(main_text(page)), name
