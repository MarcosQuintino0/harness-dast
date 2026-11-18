"""Confere, sobre a coleta real e sem Docker, que os pedaços cobrem os testes sem repetir."""

from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from _pytest.mark.expression import Expression

from tests.integration.lab_round import (
    MAP,
    PLANNED_LEVELS,
    Piece,
    PlannedLevel,
    collect_node_ids,
    load_map,
    plan_pieces,
    select_level,
)

pytestmark = pytest.mark.contract


@pytest.fixture(scope="module")
def collected() -> dict[PlannedLevel, tuple[str, ...]]:
    areas = load_map(MAP)
    result: dict[PlannedLevel, tuple[str, ...]] = {}
    for level in PLANNED_LEVELS:
        selection = select_level(level, areas)
        assert selection is not None
        result[level] = collect_node_ids(selection)
    return result


def _selected(piece: Piece, ids: Sequence[str]) -> list[str]:
    """Testes que o pytest rodaria para o pedaço: marcador, arquivo, `-k` e `--deselect`."""
    chosen = [
        i for i in ids if Path(i.split("::")[0]).name == piece.file and i not in piece.deselect
    ]
    if piece.keyword is None:
        return chosen
    expression = Expression.compile(piece.keyword)
    return [i for i in chosen if expression.evaluate(_matcher(i))]


def _matcher(node_id: str) -> Callable[..., bool]:
    last = node_id.split("::")[-1].lower()

    def match(name: str, /, **_attributes: str | int | bool | None) -> bool:
        return name.lower() in last

    return match


def test_pedacos_de_tudo_somam_a_uniao_dos_niveis_sem_perda_nem_duplicacao(
    collected: dict[PlannedLevel, tuple[str, ...]],
) -> None:
    areas = load_map(MAP)

    by_marker = {
        selection.marker: collected[level]
        for level in PLANNED_LEVELS
        if (selection := select_level(level, areas)) is not None
    }

    pieces = plan_pieces("tudo", areas, lambda selection: by_marker[selection.marker])
    runs = Counter(i for piece in pieces for i in _selected(piece, collected[piece.level]))

    union = {i for ids in collected.values() for i in ids}
    assert set(runs) == union, "teste sem pedaço"
    assert [i for i, count in runs.items() if count > 1] == [], "teste em mais de um pedaço"


@pytest.mark.parametrize("level", PLANNED_LEVELS)
def test_pedacos_de_um_nivel_cobrem_exatamente_a_coleta_do_nivel(
    collected: dict[PlannedLevel, tuple[str, ...]], level: PlannedLevel
) -> None:
    areas = load_map(MAP)
    selection = select_level(level, areas)
    assert selection is not None

    pieces = plan_pieces(level, areas, lambda _selection: collected[level])

    runs = Counter(i for piece in pieces for i in _selected(piece, collected[level]))

    assert set(runs) == set(collected[level])
    assert max(runs.values()) == 1
