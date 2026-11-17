"""Contrato sintético do mapa JSON de estatísticas do ZAP 2.17."""

import pytest
from pydantic import ValidationError

from tests.integration.oast_support import CALLBACK_INTERACTIONS, parse_interaction_count


def test_contador_zero_quando_mapa_vazio() -> None:
    assert parse_interaction_count({}) == 0


def test_contador_nao_zero_quando_retorno_oficial_plano() -> None:
    assert parse_interaction_count({CALLBACK_INTERACTIONS: "12"}) == 12


def test_contador_zero_quando_prefixo_tem_apenas_outra_estatistica() -> None:
    assert parse_interaction_count({CALLBACK_INTERACTIONS + ".outro": "1"}) == 0


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {"stats": {}},
        {"code": "does_not_exist"},
        {"outra.estatistica": "1"},
        {CALLBACK_INTERACTIONS: None},
        {CALLBACK_INTERACTIONS: 1},
        {CALLBACK_INTERACTIONS: True},
        {CALLBACK_INTERACTIONS: ""},
        {CALLBACK_INTERACTIONS: "-1"},
        {CALLBACK_INTERACTIONS: "1.5"},
        {CALLBACK_INTERACTIONS: "\uff11\uff12"},
        {CALLBACK_INTERACTIONS: "1", CALLBACK_INTERACTIONS + ".outro": "inválido"},
    ],
)
def test_recusa_resposta_invalida_ou_malformada(result: object) -> None:
    with pytest.raises((ValidationError, ValueError)):
        parse_interaction_count(result)
