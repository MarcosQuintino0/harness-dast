"""Contrato da decodificação estrita compartilhada pelos arquivos consultivos."""

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strict_json import parse_strict_json


@pytest.mark.parametrize("data", ['{"a": [1, null]}', b'{"a": [1, null]}'])
def test_decodifica_quando_documento_valido(data: str | bytes) -> None:
    assert parse_strict_json(data) == {"a": [1, None]}


@pytest.mark.parametrize(
    "data",
    [
        "",
        '{"segredo":',
        '{"segredo": 1, "segredo": 2}',
        '{"a": {"segredo": 1, "segredo": 2}}',
        "NaN",
        "Infinity",
        "-Infinity",
        b"\xff",
        "[" * 10000,
    ],
)
def test_recusa_com_erro_seguro_quando_documento_invalido(data: str | bytes) -> None:
    with pytest.raises(ConfigError) as error:
        parse_strict_json(data)
    assert "segredo" not in str(error.value)
