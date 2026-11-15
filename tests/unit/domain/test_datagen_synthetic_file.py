"""Gerador `synthetic_file` do catálogo e da regra de dados (ADR 0052)."""

from datetime import UTC, datetime

import pytest

from harness_dast.adapters.datagen import GeneratorCatalogue
from harness_dast.domain.api_schema import Schema
from harness_dast.domain.datagen import DataRules
from harness_dast.domain.datagen_catalog import generator_names, get_generator, validate_args
from harness_dast.domain.errors import ConfigError
from harness_dast.domain.request_builder import ValueRequest

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def make(args: dict[str, object]) -> DataRules:
    return DataRules.from_data(
        {
            "schema_version": 1,
            "rules": [{"match": {"field": "arquivo"}, "generator": "synthetic_file", "args": args}],
        }
    )


def draw(args: dict[str, object]) -> object:
    validated = validate_args(get_generator("synthetic_file"), args)
    request = ValueRequest(
        generator="synthetic_file",
        args=validated,
        value_schema=Schema(type="string", format="binary"),
        field_path="body.arquivo",
        field_name="arquivo",
        location="body",
        operation_id="op",
        unique=False,
        counter=0,
        draw_index=0,
        run_tag="7f3a",
    )
    return GeneratorCatalogue(1, NOW)(request)


def test_the_generator_is_in_the_catalog() -> None:
    assert "synthetic_file" in generator_names()


def test_valid_args_produce_text_kind_and_name() -> None:
    assert draw({"kind": "png", "name": "foto.png"}) == "png:foto.png"


def test_no_args_gives_the_default_text_file() -> None:
    assert draw({}) == "text:synthetic.txt"


def test_a_kind_without_a_name_gets_the_default_name_of_the_kind() -> None:
    assert draw({"kind": "json"}) == "json:synthetic.json"


@pytest.mark.parametrize(
    "args",
    [
        {"kind": "svg"},
        {"kind": "exe"},
        {"kind": 1},
        {"kind": "png", "name": "foto.txt"},
        {"kind": "png", "name": "a/b.png"},
        {"kind": "png", "name": "..png"},
        {"kind": "png", "name": 'a".png'},
        {"kind": "png", "name": "a\r\nX: y.png"},
        {"kind": "png", "name": ""},
        {"kind": "png", "name": "a" * 70 + ".png"},
        {"kind": "png", "name": 5},
        {"name": "foto.png"},
        {"desconhecido": 1},
    ],
)
def test_a_synthetic_file_rule_with_invalid_args_is_a_rule_error(args: dict[str, object]) -> None:
    with pytest.raises(ConfigError) as info:
        make(args)

    assert "rules[0]" in info.value.message or "rules" in str(info.value.message)


def test_a_valid_rule_is_accepted_and_resolved_for_the_field() -> None:
    rules = make({"kind": "csv", "name": "d.csv"})

    resolved = rules.resolve("op", "body", ("arquivo",))

    assert resolved is not None
    assert resolved.rule.generator == "synthetic_file"


def test_synthetic_file_does_not_accept_unique() -> None:
    with pytest.raises(ConfigError):
        DataRules.from_data(
            {
                "schema_version": 1,
                "rules": [
                    {
                        "match": {"field": "arquivo"},
                        "generator": "synthetic_file",
                        "unique": True,
                    }
                ],
            }
        )
