import pytest

from harness_dast.adapters.storage.strict_yaml import parse_profile_yaml
from harness_dast.domain.errors import ConfigError

SECRET = "S3nh4-Literal-Que-Nao-Pode-Vazar"  # noqa: S105 - sentinela para provar que não vaza


def _message(text: str) -> str:
    with pytest.raises(ConfigError) as caught:
        parse_profile_yaml(text)
    return f"{caught.value.message} {caught.value.hint}"


def test_parse_returns_mapping_when_yaml_is_plain() -> None:
    data = parse_profile_yaml("schema_version: 1\nscope:\n  allow: [a, b]\n  when: 2027-01-31\n")

    assert data["schema_version"] == 1
    assert isinstance(data["scope"], dict)


def test_parse_accepts_crlf_line_endings() -> None:
    assert parse_profile_yaml("a: 1\r\nb:\r\n  - x\r\n  - y\r\n") == {"a": 1, "b": ["x", "y"]}


def test_parse_rejects_anchor_with_position() -> None:
    message = _message("base: &b\n  x: 1\n")

    assert "âncora" in message
    assert "linha 1" in message


def test_parse_rejects_alias() -> None:
    message = _message("base: &b 1\ncopy: *b\n")

    assert "âncora" in message or "alias" in message


def test_parse_rejects_alias_reference_even_without_anchor_definition() -> None:
    assert "alias" in _message("copy: *undefined\n")


def test_parse_rejects_merge_key() -> None:
    message = _message("a:\n  <<: {x: 1}\n  y: 2\n")

    assert "mesclagem" in message
    assert "linha 2" in message


def test_parse_rejects_duplicate_key_with_position() -> None:
    message = _message("deny_paths: [/a]\nlimits: {}\ndeny_paths: []\n")

    assert "repetida" in message
    assert "linha 3" in message


def test_parse_rejects_duplicate_key_in_nested_mapping() -> None:
    assert "repetida" in _message("a:\n  b: 1\n  b: 2\n")


@pytest.mark.parametrize(
    "text",
    [
        "x: !!python/object:os.system {}\n",
        "x: !!python/object/apply:os.system ['echo']\n",
        "x: !!binary aGVsbG8=\n",
        "x: !!set {a, b}\n",
        "x: !!omap [a: 1]\n",
        "x: !custom 1\n",
        "x: !!timestamp 2027-01-31\n",
        "!!python/object:os.system {}\n",
    ],
)
def test_parse_rejects_tag_outside_core_schema(text: str) -> None:
    assert "tag" in _message(text) or "não é um YAML válido" in _message(text)


def test_parse_accepts_explicit_core_tags() -> None:
    assert parse_profile_yaml("a: !!str 1\nb: !!int '2'\nc: !!bool 'true'\n") == {
        "a": "1",
        "b": 2,
        "c": True,
    }


def test_parse_rejects_non_string_key() -> None:
    assert "não é texto" in _message("1: a\n")
    assert "não é texto" in _message("? [a, b]\n: c\n")


def test_parse_rejects_empty_document() -> None:
    assert "vazio" in _message("")
    assert "vazio" in _message("# só um comentário\n")


@pytest.mark.parametrize("text", ["- a\n- b\n", "texto solto\n", "42\n"])
def test_parse_rejects_root_that_is_not_a_mapping(text: str) -> None:
    assert "mapa" in _message(text)


def test_parse_rejects_multiple_documents() -> None:
    assert "não é um YAML válido" in _message("a: 1\n---\nb: 2\n")


def test_parse_reports_syntax_error_position_without_echoing_content() -> None:
    message = _message(f"a: 1\nb: [{SECRET}, \n  c: : :\n")

    assert "linha" in message
    assert SECRET not in message


def test_parse_does_not_echo_secret_when_construct_is_forbidden() -> None:
    message = _message(f"x: &ancora {SECRET}\n")

    assert SECRET not in message


def test_parse_rejects_control_characters_without_echo() -> None:
    message = _message(f"a: {SECRET}\x00\n")

    assert SECRET not in message
    assert "YAML" in message


def test_parse_rejects_deep_nesting_instead_of_crashing() -> None:
    text = "[" * 5000 + "]" * 5000

    assert "aninhamento" in _message(text)


def test_parse_rejects_deep_block_nesting() -> None:
    text = "".join("  " * level + "k:\n" for level in range(60)) + "  " * 60 + "v: 1\n"

    assert "aninhamento" in _message(text)
