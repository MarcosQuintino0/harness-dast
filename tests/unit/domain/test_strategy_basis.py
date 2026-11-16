"""Vínculo de escolha às fontes efetivamente observadas."""

from datetime import UTC, datetime

import pytest

from harness_dast.domain.errors import ConfigError
from harness_dast.domain.strategy import Strategy
from harness_dast.domain.strategy_basis import digest_strategy_document, make_strategy_basis
from tests.fakes.profile_data import valid_profile
from tests.unit.domain.test_strategy import choice, data


def test_documento_ausente_difere_de_vazio() -> None:
    assert digest_strategy_document(None) != digest_strategy_document(b"")


def test_motor_indisponivel_nao_gera_vinculo() -> None:
    digest = digest_strategy_document(b"x")
    assert (
        make_strategy_basis(
            valid_profile(),
            openapi_sha256=digest,
            data_rules_sha256=digest,
            flows_sha256=digest,
            engine_version=None,
        )
        is None
    )


@pytest.mark.parametrize(
    "field",
    ["environment", "authorization", "accounts", "openapi", "data_rules", "flows", "engine"],
)
def test_alteracao_de_qualquer_dependencia_invalida_escolha(field: str) -> None:
    digest = digest_strategy_document(b"x")
    basis = make_strategy_basis(
        valid_profile(),
        openapi_sha256=digest,
        data_rules_sha256=digest,
        flows_sha256=digest,
        engine_version="2.17",
    )
    assert basis is not None
    strategy = Strategy.from_data({**data(), "choices": [choice(basis=basis.model_dump())]})
    current = basis.model_copy(update={field: "0" * 64})
    with pytest.raises(ConfigError):
        strategy.ensure_compilable(datetime(2026, 11, 16, tzinfo=UTC), current)


def test_ausencia_de_vinculo_nunca_valida_escolha() -> None:
    strategy = Strategy.from_data({**data(), "choices": [choice()]})
    with pytest.raises(ConfigError):
        strategy.ensure_compilable(datetime(2026, 11, 16, tzinfo=UTC))
