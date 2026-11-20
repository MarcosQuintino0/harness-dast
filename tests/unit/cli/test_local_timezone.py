"""Fuso da janela padrão do pedido mínimo, vindo do ambiente (ADR 0120)."""

import pytest

from harness_dast.cli.composition import local_timezone_name


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"TZ": "UTC"}, "UTC"),
        ({"TZ": "Europe/Lisbon"}, "Europe/Lisbon"),
        ({"TZ": " America/Manaus "}, "America/Manaus"),
        ({}, "America/Sao_Paulo"),
        ({"TZ": ""}, "America/Sao_Paulo"),
        ({"TZ": "Marte/Olympus"}, "America/Sao_Paulo"),
        ({"TZ": "../etc/passwd"}, "America/Sao_Paulo"),
        ({"TZ": "BRT3"}, "America/Sao_Paulo"),
    ],
)
def test_local_timezone_name_returns_a_valid_iana_name(env: dict[str, str], expected: str) -> None:
    assert local_timezone_name(env) == expected
