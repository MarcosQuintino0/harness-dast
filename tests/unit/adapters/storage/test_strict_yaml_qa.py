# ruff: noqa: S311, SIM105, S105
"""QA independente do leitor de YAML endurecido (`adapters/storage/strict_yaml.py`).

Contrato (docstring): âncora, alias, `<<`, tag fora do esquema básico, chave repetida ou não
textual, aninhamento excessivo, documento vazio, mais de um documento e raiz que não é mapa
viram `ConfigError` com linha e coluna, nunca com o conteúdo. NENHUMA outra exceção pode escapar.
"""

import pytest

from harness_dast.adapters.storage.strict_yaml import MAX_PROFILE_BYTES, parse_yaml_document
from harness_dast.domain.errors import ConfigError


def parse(text: str) -> dict[str, object]:
    return parse_yaml_document(text, "target.yml")


def test_parse_returns_the_mapping_for_plain_yaml() -> None:
    assert parse("a: 1\nb: [x, y]\nc: {d: true}\n") == {"a": 1, "b": ["x", "y"], "c": {"d": True}}


@pytest.mark.parametrize(
    "text",
    [
        "a: &x 1\nb: *x\n",
        "a: &x [1]\n",
        "a: *x\n",
        "a: {<<: {b: 1}}\n",
        "base: &b {x: 1}\nout:\n  <<: *b\n",
        "a: !!python/object/apply:os.system ['echo oi']\n",
        "a: !!python/name:os.system\n",
        "a: !!binary aGVsbG8=\n",
        "a: !!set {x}\n",
        "a: !!omap [b: 1]\n",
        "a: !custom x\n",
        "a: 1\na: 2\n",
        "a:\n  b: 1\n  b: 2\n",
        "1: a\n",
        "~: a\n",
        "true: a\n",
        "? [a, b]\n: c\n",
        "? {a: 1}\n: c\n",
        "a: 1\n---\nb: 2\n",
        "",
        "   \n",
        "# so comentario\n",
        "- a\n- b\n",
        "just text\n",
        "42\n",
        "a: [\n",
        "a: 'sem fim\n",
        "a:\n\tb: 1\n",
        "a: \x00\n",
        "\x00",
    ],
)
def test_parse_refuses_dangerous_or_malformed_yaml_with_config_error(text: str) -> None:
    with pytest.raises(ConfigError):
        parse(text)


@pytest.mark.parametrize("depth", [41, 100, 5_000])
def test_parse_refuses_deeply_nested_flow_and_block_yaml(depth: int) -> None:
    flow = "a: " + "[" * depth + "]" * depth
    block = "".join("  " * n + f"k{n}:\n" for n in range(depth)) + "  " * depth + "x: 1\n"

    for text in (flow, block):
        with pytest.raises(ConfigError):
            parse(text)


def test_parse_error_never_echoes_the_content_of_the_file() -> None:
    secret = "SENHA-DIGITADA-NO-LUGAR-ERRADO"
    for text in (
        f"a: &x {secret}\nb: *x\n",
        f"a: !!python/object:{secret} x\n",
        f"{secret}: 1\n{secret}: 2\n",
    ):
        with pytest.raises(ConfigError) as caught:
            parse(text)

        assert secret not in caught.value.message
        assert secret not in (caught.value.hint or "")


def test_parse_reports_line_and_column_for_a_forbidden_construct() -> None:
    with pytest.raises(ConfigError) as caught:
        parse("a: 1\nb: &x 2\n")

    assert "linha 2" in caught.value.message


@pytest.mark.parametrize("digits", [4_301, 5_000, 100_000])
def test_parse_refuses_integers_beyond_the_python_conversion_limit_with_config_error(
    digits: int,
) -> None:
    # Defeito: o inteiro enorme faz o PyYAML levantar `ValueError` (limite de 4300 dígitos do
    # Python) e a exceção NÃO é `ConfigError`: escapa como erro interno (saída 10, com traceback
    # no log) em vez de erro de configuração (saída 2). Cabe num arquivo de 256 KiB.
    text = "a: " + "9" * digits + "\n"
    assert len(text) < MAX_PROFILE_BYTES

    with pytest.raises(ConfigError):
        parse(text)


@pytest.mark.parametrize(
    "text",
    [
        "a: .nan\n",
        "a: .inf\n",
        "a: 2026-11-13\n",
        "a: 2026-11-13 10:00:00\n",
        "a: 0777\n",
        "a: 0o17\n",
        "a: 0x1F\n",
        "a: 1_000\n",
        "a: yes\n",
        "a: null\n",
        "'': x\n",
        "a\u200b: 1\n",
        "\ufeffa: 1\n",
    ],
)
def test_parse_never_raises_anything_but_config_error_for_odd_scalars(text: str) -> None:
    try:
        result = parse(text)
    except ConfigError:
        return

    assert isinstance(result, dict)


def test_parse_never_raises_anything_but_config_error_on_random_garbage() -> None:
    import random

    rng = random.Random(1234)
    alphabet = "ab:-[]{}&*!|>'\"#,?%@`\t \n0123456789.~"
    for _ in range(3_000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60)))
        try:
            parse(text)
        except ConfigError:
            pass
