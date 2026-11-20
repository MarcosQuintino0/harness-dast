from datetime import date

import pytest
import yaml

from harness_dast.domain.letter_yaml import render_yaml


def test_render_yaml_writes_nested_blocks_in_insertion_order() -> None:
    text = render_yaml({"b": {"y": 1, "x": True}, "a": ["um", "dois"]})

    assert text == 'b:\n  y: 1\n  x: true\na:\n  - "um"\n  - "dois"\n'


def test_render_yaml_writes_a_list_of_maps_with_the_dash_on_the_first_key() -> None:
    text = render_yaml({"items": [{"k": "v", "n": 2}, {"k": "w"}]})

    assert text == 'items:\n  - k: "v"\n    n: 2\n  - k: "w"\n'


def test_render_yaml_writes_empty_containers_inline() -> None:
    assert render_yaml({"a": [], "b": {}}) == "a: []\nb: {}\n"


def test_render_yaml_writes_dates_without_quotes_and_integral_floats_as_integers() -> None:
    text = render_yaml({"d": date(2027, 12, 31), "f": 5.0, "g": 0.5})

    assert text == "d: 2027-12-31\nf: 5\ng: 0.5\n"


def test_render_yaml_rejects_a_type_it_does_not_know() -> None:
    with pytest.raises(TypeError):
        render_yaml({"a": object()})


@pytest.mark.parametrize(
    "text",
    [
        'aspas "duplas" e \\ barra',
        "linha\nquebrada\ttab",
        "separador\u2028de\u2029linha",
        "ação, médico: não # comentário",
        "true",
        "null",
        "123",
        "- item",
        "{a: b}",
        "emoji \U0001f600 fora do plano básico",
        "nulo\x00aqui",
        "",
    ],
)
def test_render_yaml_roundtrips_any_text_through_a_yaml_parser(text: str) -> None:
    rendered = render_yaml({"k": text, "list": [text]})

    assert yaml.safe_load(rendered) == {"k": text, "list": [text]}


def test_render_yaml_is_identical_on_every_call() -> None:
    data = {"a": [{"x": "é", "y": [1, 2]}], "b": {"c": date(2030, 1, 2)}}

    assert render_yaml(data) == render_yaml(data)
