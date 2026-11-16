"""Validação conservadora da estratégia, sem eco de entradas externas."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import StrategyBasis

_BASIS = StrategyBasis(
    **{
        key: "a" * 64
        for key in (
            "environment",
            "authorization",
            "accounts",
            "planning",
            "openapi",
            "data_rules",
            "flows",
            "engine",
        )
    }
)


def data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "references": {
            "target": "target.yml",
            "data_rules": "data-rules.yml",
            "flows": "flows.yml",
        },
        "choices": [],
    }


def choice(**changes: object) -> dict[str, object]:
    return {
        "name": "coverage",
        "value": "preserve",
        "source": "observation",
        "reason": "preserve_baseline",
        "valid_until": "2026-11-16",
        "state": "validated",
        **changes,
    }


def test_estrategia_vazia_e_valida_para_compilacao() -> None:
    Strategy.from_data(data()).ensure_compilable(datetime(2026, 11, 16, tzinfo=UTC))


def test_escolha_preservar_com_validade_no_dia_e_aceita() -> None:
    strategy = Strategy.from_data({**data(), "choices": [choice(basis=_BASIS.model_dump())]})

    strategy.ensure_compilable(datetime(2026, 11, 16, tzinfo=UTC), _BASIS)


def test_validade_usa_data_utc_na_borda_do_fuso() -> None:
    strategy = Strategy.from_data({**data(), "choices": [choice()]})
    with pytest.raises(ConfigError):
        strategy.ensure_compilable(datetime(2026, 11, 16, 22, tzinfo=timezone(-timedelta(hours=3))))


@pytest.mark.parametrize(
    "changes", [{"state": "proposed"}, {"state": "review_required"}, {"valid_until": "2026-11-15"}]
)
def test_compilacao_recusa_escolha_pendente_ou_vencida(changes: dict[str, object]) -> None:
    strategy = Strategy.from_data({**data(), "choices": [choice(**changes)]})
    with pytest.raises(ConfigError):
        strategy.ensure_compilable(datetime(2026, 11, 16, tzinfo=UTC))


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        {**data(), "schema_version": True},
        {**data(), "choices": [choice(), choice()]},
        {**data(), "choices": [choice(valid_until="nan")]},
        {**data(), "choices": [choice(value="alterar")]},
        {
            **data(),
            "references": {
                "target": "../segredo",
                "data_rules": "data-rules.yml",
                "flows": "flows.yml",
            },
        },
    ],
)
def test_entrada_invalida_falha_sem_eco(invalid: object) -> None:
    with pytest.raises(ConfigError) as caught:
        Strategy.from_data(invalid)
    assert "segredo" not in str(caught.value)


def test_campo_desconhecido_nao_e_repetido_no_erro() -> None:
    with pytest.raises(ConfigError) as caught:
        Strategy.from_data({**data(), "senha-secreta": "valor-secreto"})
    assert "segredo" not in str(caught.value)
